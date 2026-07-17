/**
 * LLMJudgeSource -- slop-eval's first-party RuleSource implementation.
 *
 * Scores a URL or screenshot against the rubric in src/rubric/<name>.json by
 * calling the Anthropic API with a forced tool call, so the response is
 * reliably parseable JSON rather than free text that has to be regex'd out
 * of a chat reply.
 *
 * v0.1 input handling:
 *   - `screenshotPath` is the well-supported path: the image is read and
 *     sent to the judge as base64, giving it a real rendered view of the UI.
 *   - `url` is a documented v0.1 fallback: this tool does not bundle a
 *     headless browser (Playwright/Puppeteer) to render the page into a
 *     screenshot -- that's an intentional v0.1 scope decision. Instead the
 *     raw HTML/text response body is fetched and
 *     given to the judge as text. The judge can reason about markup, inline
 *     styles, and copy, but not the actual rendered visual layout -- so
 *     --screenshot is the stronger signal. This limitation is also stated in
 *     the CLI's --help text.
 *
 * Every real judge call is wrapped through the content-hash cache in
 * src/cache/judge-cache.ts, so identical input never triggers a second API
 * call.
 *
 * Along with composite.ts, this module directly produces the CI-gate
 * verdict, so it carries a 95%+ coverage requirement -- the real Anthropic
 * API is never called in tests; every test mocks the client.
 */

import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';
import * as dns from 'dns';
import * as net from 'net';
import Anthropic from '@anthropic-ai/sdk';
import type { RuleFinding, RuleSource, ScoreInput } from './RuleSource';
import { getCachedOrCompute } from '../cache/judge-cache';

/** Thrown when ANTHROPIC_API_KEY is not set. Distinguished from other errors so the CLI can map it to exit code 2 with a clear, actionable message. */
export class MissingApiKeyError extends Error {
  constructor() {
    super(
      'ANTHROPIC_API_KEY environment variable is not set.\n' +
        'slop-eval calls the Anthropic API to run the LLM judge, and is BYO-key ' +
        '(bring your own key) -- there is no default or shared key baked into this ' +
        'tool. Set your key and try again:\n\n' +
        '  export ANTHROPIC_API_KEY="sk-ant-..."\n\n' +
        'Get a key at https://console.anthropic.com/',
    );
    this.name = 'MissingApiKeyError';
  }
}

/** Thrown when the requested rubric file is missing or malformed. Maps to exit code 2. */
export class RubricLoadError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RubricLoadError';
  }
}

interface RubricCategory {
  id: string;
  name: string;
  description: string;
}

interface Rubric {
  version: string;
  description: string;
  categories: RubricCategory[];
}

interface JudgeImageInput {
  kind: 'image';
  base64: string;
  mediaType: 'png' | 'jpeg' | 'gif' | 'webp';
}

interface JudgeTextInput {
  kind: 'text';
  url: string;
  text: string;
}

type JudgeInput = JudgeImageInput | JudgeTextInput;

interface JudgeCategoryResult {
  categoryId: string;
  score: number;
  evidence: string;
}

/** Default model per this repo's rubric task: a rubric-scoring judge is a bounded classification/extraction call against a fixed rubric, not open-ended reasoning, so a mid-tier model is the right cost/quality default for a BYO-key tool invoked repeatedly in CI. Override with ANTHROPIC_MODEL for teams that want a more capable judge. */
const DEFAULT_MODEL = 'claude-sonnet-5';

/** Hard cap on how long --url mode will wait for the page fetch. Without this, a target URL that never completes the response (a hung dev-preview deploy, a slow proxy, a streaming endpoint that never closes) hangs the whole CI job until the runner's own top-level timeout kills it -- minutes to hours later -- instead of failing fast with an actionable error. Override with SLOP_EVAL_FETCH_TIMEOUT_MS for slower targets. */
const URL_FETCH_TIMEOUT_MS = Number(process.env.SLOP_EVAL_FETCH_TIMEOUT_MS) || 30_000;

/** Best-effort cap on response body size for --url mode, checked against the Content-Length header when the server reports one. This does not stop a server that lies about or omits Content-Length while streaming an unbounded body -- closing that gap fully requires reading the body incrementally with a hard byte cap, which is out of scope for this fix -- but it does stop the common case of an honestly-huge page (a large export, a misrouted binary/video asset) from being read fully into memory before the 20000-char slice ever helps. */
const URL_MAX_CONTENT_LENGTH_BYTES = 10 * 1024 * 1024;

// --rubric is joined straight into a filesystem path below; restricting it
// to a bare name (no separators or ".." segments) before that join closes
// off path traversal for any caller that ever wires --rubric to something
// other than a maintainer-chosen local flag.
const RUBRIC_NAME_PATTERN = /^[\w-]+$/;

/** Resolves the rubric file path for `rubricName`, relative to the package root's src/rubric/ directory (works both from ts-node against source and from dist/ once built, as long as src/ ships alongside dist/ -- see package.json's `files` field). */
function resolveRubricPath(rubricName: string): string {
  if (!RUBRIC_NAME_PATTERN.test(rubricName)) {
    throw new RubricLoadError(
      `Rubric name "${rubricName}" is invalid -- expected letters, digits, "-", or "_" only.`,
    );
  }
  // __dirname is src/sources (source) or dist/sources (compiled) -- either
  // way, ../../src/rubric is the project's src/rubric directory.
  return path.resolve(__dirname, '..', '..', 'src', 'rubric', `${rubricName}.json`);
}

export function loadRubric(rubricName: string): Rubric {
  const rubricPath = resolveRubricPath(rubricName);

  if (!fs.existsSync(rubricPath)) {
    throw new RubricLoadError(
      `Rubric "${rubricName}" not found (looked for ${rubricPath}). ` +
        'Available rubrics live in src/rubric/*.json -- pass --rubric with one of those names (without the .json extension).',
    );
  }

  let raw: string;
  try {
    raw = fs.readFileSync(rubricPath, 'utf-8');
  } catch (err) {
    throw new RubricLoadError(
      `Could not read rubric file at ${rubricPath}: ${(err as Error).message}`,
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    throw new RubricLoadError(
      `Rubric file at ${rubricPath} is not valid JSON: ${(err as Error).message}`,
    );
  }

  if (
    typeof parsed !== 'object' ||
    parsed === null ||
    !Array.isArray((parsed as Rubric).categories) ||
    (parsed as Rubric).categories.length === 0
  ) {
    throw new RubricLoadError(
      `Rubric file at ${rubricPath} is malformed: expected a "categories" array with at least one entry.`,
    );
  }

  for (const cat of (parsed as Rubric).categories) {
    if (!cat.id || !cat.name || !cat.description) {
      throw new RubricLoadError(
        `Rubric file at ${rubricPath} has a category missing "id", "name", or "description": ${JSON.stringify(cat)}`,
      );
    }
  }

  return parsed as Rubric;
}

/**
 * Blocks SSRF into internal/cloud-metadata targets before --url mode fetches
 * anything. This tool is meant to be embedded in other people's CI (via the
 * bundled GitHub Action), where --url can end up wired to PR-derived input --
 * without this, a crafted target (a private RFC1918 address, or the
 * 169.254.169.254 cloud-metadata endpoint, which falls under the link-local
 * block below) would be fetched and its response handed to the LLM judge,
 * with the risk of sensitive content resurfacing in the JSON output.
 *
 * This validates the resolved IP at lookup time, not at connection time, so
 * it does not fully close a DNS-rebinding attack (a name that resolves to a
 * public IP during this check but a private one when Node actually
 * connects) -- fully closing that requires a custom dispatcher that
 * re-validates the IP it connects to, which is out of scope for this fix.
 */
async function assertUrlIsSafeToFetch(rawUrl: string): Promise<void> {
  // Callers wrap thrown messages as `Could not fetch URL ${url}: ${message}`
  // -- keep messages here to just the reason, not a re-stated "Could not
  // fetch URL" prefix.
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new Error('not a valid URL.');
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error(`only http/https URLs are supported for --url mode (got "${parsed.protocol}").`);
  }
  const hostname = parsed.hostname;
  if (!hostname || hostname.toLowerCase() === 'metadata.google.internal') {
    throw new Error(`host "${hostname}" is not allowed for --url mode.`);
  }
  let addresses: string[];
  try {
    addresses = (await dns.promises.lookup(hostname, { all: true })).map((a) => a.address);
  } catch (err) {
    throw new Error(`could not resolve host "${hostname}": ${(err as Error).message}`);
  }
  for (const address of addresses) {
    if (isPrivateOrReservedIp(address)) {
      throw new Error(
        `host "${hostname}" resolves to a private/internal address (${address}), which is not allowed for --url mode.`,
      );
    }
  }
}

function isPrivateOrReservedIp(address: string): boolean {
  if (net.isIPv4(address)) {
    const [a, b] = address.split('.').map(Number);
    if (a === 127) return true; // loopback
    if (a === 10) return true; // RFC1918 private
    if (a === 172 && b >= 16 && b <= 31) return true; // RFC1918 private
    if (a === 192 && b === 168) return true; // RFC1918 private
    if (a === 169 && b === 254) return true; // link-local, incl. cloud metadata (169.254.169.254)
    if (a === 100 && b >= 64 && b <= 127) return true; // CGNAT (RFC6598)
    if (a === 0) return true; // "this network"
    if (a >= 224) return true; // multicast + reserved
    return false;
  }
  if (net.isIPv6(address)) {
    const lower = address.toLowerCase();
    if (lower === '::1' || lower === '::') return true; // loopback / unspecified
    if (lower.startsWith('fe8') || lower.startsWith('fe9') || lower.startsWith('fea') || lower.startsWith('feb')) {
      return true; // link-local fe80::/10
    }
    if (lower.startsWith('fc') || lower.startsWith('fd')) return true; // unique local fc00::/7
    if (lower.startsWith('::ffff:')) {
      const mapped = lower.slice('::ffff:'.length);
      if (net.isIPv4(mapped)) return isPrivateOrReservedIp(mapped);
    }
    return false;
  }
  return true; // unrecognized address format -- fail closed
}

export class LLMJudgeSource implements RuleSource {
  name = 'llm-judge';

  private rubric: Rubric;
  private client: Anthropic | undefined;
  private cacheDir: string | undefined;
  private model: string;

  /**
   * @param rubricName which rubric/<name>.json to load and score against.
   * @param cacheDir override the judge-cache directory (mainly for tests).
   * @param model override the Anthropic model id (defaults to ANTHROPIC_MODEL env var, then DEFAULT_MODEL).
   */
  constructor(rubricName: string = 'v1', cacheDir?: string, model?: string) {
    this.rubric = loadRubric(rubricName);
    this.cacheDir = cacheDir;
    this.model = model ?? process.env.ANTHROPIC_MODEL ?? DEFAULT_MODEL;
  }

  private getClient(): Anthropic {
    if (this.client) {
      return this.client;
    }
    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
      throw new MissingApiKeyError();
    }
    this.client = new Anthropic({ apiKey });
    return this.client;
  }

  async score(input: ScoreInput): Promise<RuleFinding[]> {
    const { judgeInput, hash } = await this.loadInput(input);
    return getCachedOrCompute(hash, () => this.callJudge(judgeInput), this.cacheDir);
  }

  private async loadInput(input: ScoreInput): Promise<{ judgeInput: JudgeInput; hash: string }> {
    if (input.screenshotPath) {
      let bytes: Buffer;
      try {
        bytes = fs.readFileSync(input.screenshotPath);
      } catch (err) {
        throw new Error(
          `Could not read screenshot at ${input.screenshotPath}: ${(err as Error).message}`,
        );
      }
      const hash = crypto.createHash('sha256').update(bytes).digest('hex');
      const ext = path.extname(input.screenshotPath).toLowerCase().replace('.', '');
      const mediaType: JudgeImageInput['mediaType'] =
        ext === 'jpg' || ext === 'jpeg'
          ? 'jpeg'
          : ext === 'gif'
            ? 'gif'
            : ext === 'webp'
              ? 'webp'
              : 'png';
      return {
        judgeInput: { kind: 'image', base64: bytes.toString('base64'), mediaType },
        hash,
      };
    }

    if (input.url) {
      let text: string;
      try {
        await assertUrlIsSafeToFetch(input.url);
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), URL_FETCH_TIMEOUT_MS);
        let res: Response;
        try {
          res = await fetch(input.url, { signal: controller.signal });
        } finally {
          clearTimeout(timer);
        }
        if (!res.ok) {
          throw new Error(`HTTP ${res.status} ${res.statusText}`);
        }
        const contentLength = Number(res.headers?.get?.('content-length'));
        if (Number.isFinite(contentLength) && contentLength > URL_MAX_CONTENT_LENGTH_BYTES) {
          throw new Error(
            `response body (${contentLength} bytes) exceeds the ${URL_MAX_CONTENT_LENGTH_BYTES}-byte cap for --url mode -- ` +
              'render the page yourself and pass --screenshot instead.',
          );
        }
        text = await res.text();
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          throw new Error(
            `Could not fetch URL ${input.url}: timed out after ${URL_FETCH_TIMEOUT_MS}ms`,
          );
        }
        throw new Error(`Could not fetch URL ${input.url}: ${(err as Error).message}`);
      }
      const hash = crypto
        .createHash('sha256')
        .update(`${input.url}\n${text}`)
        .digest('hex');
      return { judgeInput: { kind: 'text', url: input.url, text }, hash };
    }

    throw new Error('ScoreInput requires either "url" or "screenshotPath" to be set.');
  }

  private async callJudge(judgeInput: JudgeInput): Promise<RuleFinding[]> {
    const client = this.getClient();
    const categories = this.rubric.categories;

    const rubricText = categories
      .map((c) => `- id: "${c.id}" (${c.name}) -- ${c.description}`)
      .join('\n');

    const instructions =
      judgeInput.kind === 'image'
        ? 'You are scoring a screenshot of an AI-generated web UI for genericness ("slop") against the rubric below. ' +
          'For each rubric category, give a 0-10 score (0 = maximally generic/derivative, 10 = maximally distinctive/original) ' +
          'and a specific, cited evidence string describing exactly what you observed -- never a generic statement like ' +
          '"could be more original." Call the submit_slop_scores tool with one entry per category.'
        : 'You are scoring the raw HTML/text content of a web page for genericness ("slop") against the rubric below. ' +
          'Note: no rendered screenshot was available (v0.1 limitation -- URL mode has no headless-browser renderer), so ' +
          'judge from markup structure, inline styles, class names, and copy rather than final visual layout. ' +
          'For each rubric category, give a 0-10 score (0 = maximally generic/derivative, 10 = maximally distinctive/original) ' +
          'and a specific, cited evidence string describing exactly what you observed -- never a generic statement. ' +
          'Call the submit_slop_scores tool with one entry per category.';

    const promptText =
      judgeInput.kind === 'image'
        ? `${instructions}\n\nRubric categories:\n${rubricText}`
        : `${instructions}\n\nRubric categories:\n${rubricText}\n\nPage URL: ${judgeInput.url}\n\nPage content (truncated to 20000 characters):\n${judgeInput.text.slice(0, 20000)}`;

    const content: Anthropic.Messages.ContentBlockParam[] =
      judgeInput.kind === 'image'
        ? [
            {
              type: 'image',
              source: {
                type: 'base64',
                media_type: `image/${judgeInput.mediaType}` as
                  | 'image/png'
                  | 'image/jpeg'
                  | 'image/gif'
                  | 'image/webp',
                data: judgeInput.base64,
              },
            },
            { type: 'text', text: promptText },
          ]
        : [{ type: 'text', text: promptText }];

    const toolSchema: Anthropic.Messages.Tool = {
      name: 'submit_slop_scores',
      description: 'Submit a 0-10 score and specific evidence for every rubric category.',
      input_schema: {
        type: 'object',
        properties: {
          findings: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                categoryId: {
                  type: 'string',
                  enum: categories.map((c) => c.id),
                  description: 'Must exactly match one of the rubric category ids.',
                },
                score: {
                  type: 'number',
                  description: '0-10 score for this category.',
                },
                evidence: {
                  type: 'string',
                  description:
                    'Specific, cited reason for the score -- never a generic statement.',
                },
              },
              required: ['categoryId', 'score', 'evidence'],
            },
          },
        },
        required: ['findings'],
      },
    };

    const response = await client.messages.create({
      model: this.model,
      max_tokens: 2048,
      tools: [toolSchema],
      tool_choice: { type: 'tool', name: 'submit_slop_scores' },
      messages: [{ role: 'user', content }],
    });

    const toolUseBlock = response.content.find(
      (block): block is Anthropic.Messages.ToolUseBlock => block.type === 'tool_use',
    );

    if (!toolUseBlock) {
      throw new Error(
        'LLM judge did not return the expected structured tool-use response. This is an unexpected API response shape, not a scoring result.',
      );
    }

    const parsed = toolUseBlock.input as { findings: JudgeCategoryResult[] };

    return categories.map((cat): RuleFinding => {
      const found = parsed.findings?.find((f) => f.categoryId === cat.id);
      if (!found) {
        return {
          ruleId: `llm-judge.${cat.id}`,
          category: cat.name,
          score: 0,
          evidence: `The LLM judge did not return a finding for rubric category "${cat.name}" -- treating as unscored rather than fabricating a value.`,
          status: 'not_scored',
        };
      }
      const clampedScore = Math.max(0, Math.min(10, found.score));
      return {
        ruleId: `llm-judge.${cat.id}`,
        category: cat.name,
        score: clampedScore,
        evidence: found.evidence,
        status: clampedScore >= 6 ? 'pass' : 'flag',
      };
    });
  }
}
