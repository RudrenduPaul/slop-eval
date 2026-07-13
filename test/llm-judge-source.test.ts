import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

// Mock the Anthropic SDK before importing LLMJudgeSource so the real network
// client is never constructed. Every test in this file must never make a
// real network call.
const createMock = vi.fn();
const constructorMock = vi.fn();
vi.mock('@anthropic-ai/sdk', () => ({
  default: class MockAnthropic {
    messages = { create: createMock };
    constructor(opts: unknown) {
      constructorMock(opts);
    }
  },
}));

import {
  LLMJudgeSource,
  MissingApiKeyError,
  RubricLoadError,
  loadRubric,
} from '../src/sources/LLMJudgeSource';

const FIXTURE_PNG = path.join(__dirname, 'fixtures', 'sample.png');

function mockToolResponse(findings: { categoryId: string; score: number; evidence: string }[]) {
  createMock.mockResolvedValue({
    content: [{ type: 'tool_use', id: 'toolu_1', name: 'submit_slop_scores', input: { findings } }],
  });
}

const ALL_CATEGORIES_MEDIUM = [
  { categoryId: 'layout-novelty', score: 5, evidence: 'evidence a' },
  { categoryId: 'visual-identity-distinctiveness', score: 5, evidence: 'evidence b' },
  { categoryId: 'component-pattern-novelty', score: 5, evidence: 'evidence c' },
];

describe('LLMJudgeSource', () => {
  let tmpCacheDir: string;
  const originalKey = process.env.ANTHROPIC_API_KEY;

  beforeEach(() => {
    createMock.mockReset();
    constructorMock.mockReset();
    tmpCacheDir = fs.mkdtempSync(path.join(os.tmpdir(), 'slop-eval-llm-test-'));
    process.env.ANTHROPIC_API_KEY = 'test-key-not-real';
  });

  afterEach(() => {
    fs.rmSync(tmpCacheDir, { recursive: true, force: true });
    if (originalKey === undefined) delete process.env.ANTHROPIC_API_KEY;
    else process.env.ANTHROPIC_API_KEY = originalKey;
  });

  describe('loadRubric', () => {
    it('loads the v1 rubric with its 3 documented categories', () => {
      const rubric = loadRubric('v1');
      expect(rubric.categories).toHaveLength(3);
      expect(rubric.categories.map((c) => c.id)).toEqual([
        'layout-novelty',
        'visual-identity-distinctiveness',
        'component-pattern-novelty',
      ]);
    });

    it('throws RubricLoadError for a rubric name that does not exist', () => {
      expect(() => loadRubric('does-not-exist')).toThrow(RubricLoadError);
    });

    it('throws RubricLoadError when the rubric path exists but cannot be read as a file', () => {
      // A directory at the expected path exists (passes existsSync) but
      // readFileSync on it throws EISDIR -- exercises the read-error branch
      // distinct from the not-found branch above.
      const rubricName = `test-dir-rubric-${Date.now()}`;
      const rubricDir = path.join(__dirname, '..', 'src', 'rubric', `${rubricName}.json`);
      fs.mkdirSync(rubricDir);
      try {
        expect(() => loadRubric(rubricName)).toThrow(RubricLoadError);
        expect(() => loadRubric(rubricName)).toThrow(/Could not read rubric file/);
      } finally {
        fs.rmdirSync(rubricDir);
      }
    });

    it('throws RubricLoadError for malformed JSON', () => {
      const rubricName = `test-malformed-${Date.now()}`;
      const rubricPath = path.join(__dirname, '..', 'src', 'rubric', `${rubricName}.json`);
      fs.writeFileSync(rubricPath, '{ this is not valid json');
      try {
        expect(() => loadRubric(rubricName)).toThrow(/not valid JSON/);
      } finally {
        fs.unlinkSync(rubricPath);
      }
    });

    it('throws RubricLoadError when categories is missing or empty', () => {
      const rubricName = `test-empty-categories-${Date.now()}`;
      const rubricPath = path.join(__dirname, '..', 'src', 'rubric', `${rubricName}.json`);
      fs.writeFileSync(rubricPath, JSON.stringify({ version: 'v1', description: 'x', categories: [] }));
      try {
        expect(() => loadRubric(rubricName)).toThrow(/expected a "categories" array/);
      } finally {
        fs.unlinkSync(rubricPath);
      }
    });

    it('throws RubricLoadError when a category is missing id, name, or description', () => {
      const rubricName = `test-missing-field-${Date.now()}`;
      const rubricPath = path.join(__dirname, '..', 'src', 'rubric', `${rubricName}.json`);
      fs.writeFileSync(
        rubricPath,
        JSON.stringify({ version: 'v1', description: 'x', categories: [{ id: 'a' }] }),
      );
      try {
        expect(() => loadRubric(rubricName)).toThrow(/missing "id", "name", or "description"/);
      } finally {
        fs.unlinkSync(rubricPath);
      }
    });
  });

  it('throws MissingApiKeyError with an actionable message when ANTHROPIC_API_KEY is unset', async () => {
    delete process.env.ANTHROPIC_API_KEY;
    const source = new LLMJudgeSource('v1', tmpCacheDir);

    await expect(source.score({ screenshotPath: FIXTURE_PNG })).rejects.toThrow(MissingApiKeyError);
    await expect(source.score({ screenshotPath: FIXTURE_PNG })).rejects.toThrow(/ANTHROPIC_API_KEY/);
    expect(createMock).not.toHaveBeenCalled();
  });

  it('scores a screenshot and maps each rubric category to a finding', async () => {
    mockToolResponse([
      { categoryId: 'layout-novelty', score: 4, evidence: 'generic hero layout' },
      { categoryId: 'visual-identity-distinctiveness', score: 8, evidence: 'unique palette' },
      { categoryId: 'component-pattern-novelty', score: 7, evidence: 'custom cards' },
    ]);
    const source = new LLMJudgeSource('v1', tmpCacheDir);

    const findings = await source.score({ screenshotPath: FIXTURE_PNG });

    expect(findings).toHaveLength(3);
    expect(findings.find((f) => f.ruleId === 'llm-judge.layout-novelty')).toMatchObject({
      score: 4,
      status: 'flag',
      evidence: 'generic hero layout',
    });
    expect(findings.find((f) => f.ruleId === 'llm-judge.visual-identity-distinctiveness')).toMatchObject({
      score: 8,
      status: 'pass',
    });
    expect(createMock).toHaveBeenCalledTimes(1);
  });

  it('caches identical screenshot input so the API is called exactly once across two score() calls', async () => {
    mockToolResponse(ALL_CATEGORIES_MEDIUM);
    const source = new LLMJudgeSource('v1', tmpCacheDir);

    await source.score({ screenshotPath: FIXTURE_PNG });
    await source.score({ screenshotPath: FIXTURE_PNG });

    expect(createMock).toHaveBeenCalledTimes(1);
  });

  it('marks a rubric category not_scored if the judge response omits it', async () => {
    mockToolResponse([{ categoryId: 'layout-novelty', score: 5, evidence: 'x' }]);
    const source = new LLMJudgeSource('v1', tmpCacheDir);

    const findings = await source.score({ screenshotPath: FIXTURE_PNG });

    const notScored = findings.filter((f) => f.status === 'not_scored');
    expect(notScored).toHaveLength(2);
    expect(notScored.every((f) => f.evidence.length > 0)).toBe(true);
  });

  it('clamps out-of-range scores into 0-10', async () => {
    mockToolResponse([
      { categoryId: 'layout-novelty', score: 15, evidence: 'x' },
      { categoryId: 'visual-identity-distinctiveness', score: -3, evidence: 'x' },
      { categoryId: 'component-pattern-novelty', score: 5, evidence: 'x' },
    ]);
    const source = new LLMJudgeSource('v1', tmpCacheDir);

    const findings = await source.score({ screenshotPath: FIXTURE_PNG });

    expect(findings.find((f) => f.ruleId === 'llm-judge.layout-novelty')?.score).toBe(10);
    expect(findings.find((f) => f.ruleId === 'llm-judge.visual-identity-distinctiveness')?.score).toBe(0);
  });

  it('throws a clear error when the judge response has no tool_use block', async () => {
    createMock.mockResolvedValue({ content: [{ type: 'text', text: 'I refuse to use tools.' }] });
    const source = new LLMJudgeSource('v1', tmpCacheDir);

    await expect(source.score({ screenshotPath: FIXTURE_PNG })).rejects.toThrow(/structured tool-use/);
  });

  it('scores a URL by fetching its text content (fetch mocked -- no real network call)', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      text: async () => '<html><body><h1>Hi</h1></body></html>',
    } as unknown as Response);
    mockToolResponse(ALL_CATEGORIES_MEDIUM);
    const source = new LLMJudgeSource('v1', tmpCacheDir);

    const findings = await source.score({ url: 'https://example.com' });

    expect(findings).toHaveLength(3);
    expect(fetchMock).toHaveBeenCalledWith('https://example.com');
    fetchMock.mockRestore();
  });

  it('throws a clear error when the URL fetch returns a non-ok response', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      text: async () => '',
    } as unknown as Response);
    const source = new LLMJudgeSource('v1', tmpCacheDir);

    await expect(source.score({ url: 'https://example.com/missing' })).rejects.toThrow(/404/);
    fetchMock.mockRestore();
  });

  it('throws a clear error when the URL fetch itself rejects (network failure)', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('DNS lookup failed'));
    const source = new LLMJudgeSource('v1', tmpCacheDir);

    await expect(source.score({ url: 'https://unreachable.example' })).rejects.toThrow(/Could not fetch URL/);
    fetchMock.mockRestore();
  });

  it('throws when neither url nor screenshotPath is provided', async () => {
    const source = new LLMJudgeSource('v1', tmpCacheDir);
    await expect(source.score({})).rejects.toThrow(/requires either/);
  });

  it('throws a clear error for an unreadable screenshot path', async () => {
    const source = new LLMJudgeSource('v1', tmpCacheDir);
    await expect(source.score({ screenshotPath: '/nonexistent/path/nope.png' })).rejects.toThrow(
      /Could not read screenshot/,
    );
  });

  it('respects an explicit model override over the ANTHROPIC_MODEL env var and default', async () => {
    mockToolResponse(ALL_CATEGORIES_MEDIUM);
    const source = new LLMJudgeSource('v1', tmpCacheDir, 'claude-haiku-4-5');

    await source.score({ screenshotPath: FIXTURE_PNG });

    expect(createMock).toHaveBeenCalledWith(
      expect.objectContaining({ model: 'claude-haiku-4-5' }),
    );
  });

  it('reuses the same Anthropic client instance across two different (cache-miss) inputs on one source instance', async () => {
    mockToolResponse(ALL_CATEGORIES_MEDIUM);
    const source = new LLMJudgeSource('v1', tmpCacheDir);

    // Different byte content than FIXTURE_PNG -> different content hash ->
    // guaranteed second cache miss, so callJudge (and therefore getClient)
    // runs a second time on the *same* source instance. The client must be
    // constructed only once and reused, not re-constructed per call.
    const secondScreenshot = path.join(tmpCacheDir, 'second.png');
    fs.writeFileSync(secondScreenshot, Buffer.concat([fs.readFileSync(FIXTURE_PNG), Buffer.from([0x00])]));

    await source.score({ screenshotPath: FIXTURE_PNG });
    await source.score({ screenshotPath: secondScreenshot });

    expect(createMock).toHaveBeenCalledTimes(2);
    expect(constructorMock).toHaveBeenCalledTimes(1);
  });
});
