#!/usr/bin/env node
/**
 * slop-eval CLI entry point.
 *
 * Subcommand: `score` -- scores a URL or screenshot for AI-UI genericness
 * ("slop") using the LLM-judge rubric, plus the (v0.1 stub) screenshot-diff
 * source.
 *
 * Exit codes (per CLAUDE.md / eng-review):
 *   0 -- ran successfully, and either no --fail-below threshold was given or
 *        the composite score met it.
 *   1 -- ran successfully, but the composite score is below --fail-below.
 *   2 -- usage/input error (bad flags, missing required input) or an
 *        unrecoverable error (missing API key, unreadable file, malformed
 *        rubric).
 *
 * `--json` mode always emits valid JSON on stdout, on both success and error
 * paths, so an agent invoking this CLI programmatically gets a consistent,
 * parseable schema either way.
 */

import { Command } from 'commander';
import { LLMJudgeSource, MissingApiKeyError, RubricLoadError } from './sources/LLMJudgeSource';
import { ScreenshotDiffSource } from './sources/ScreenshotDiffSource';
import { scoreComposite } from './scorer/composite';
import { printReport } from './report/writer';
import type { RuleSource } from './sources/RuleSource';

export interface ScoreOptions {
  url?: string;
  screenshot?: string;
  rubric: string;
  json: boolean;
  failBelow?: number;
}

/** Prints an error consistently across both output modes. JSON mode always emits valid JSON (an object with an "error" key) so a programmatic caller never has to branch on success vs. failure shape to just find the error string. */
function printError(message: string, jsonMode: boolean): void {
  if (jsonMode) {
    // eslint-disable-next-line no-console -- structured stdout output, not a debug log
    console.log(JSON.stringify({ error: message }, null, 2));
  } else {
    // eslint-disable-next-line no-console -- user-facing error output
    console.error(`Error: ${message}`);
  }
}

/**
 * Runs the `score` command end-to-end and returns the process exit code.
 * Exported (rather than calling process.exit directly) so tests can invoke
 * it in-process and assert on the returned code plus captured stdout,
 * without spawning a subprocess.
 *
 * @param buildSources overridable for tests that need to inject a fake
 *   RuleSource[] instead of constructing the real LLMJudgeSource (which
 *   requires ANTHROPIC_API_KEY). Defaults to the real sources.
 */
export async function runScore(
  options: ScoreOptions,
  buildSources: (rubric: string) => RuleSource[] = (rubric) => [
    new LLMJudgeSource(rubric),
    new ScreenshotDiffSource(),
  ],
): Promise<number> {
  const { url, screenshot, rubric, json, failBelow } = options;

  if (url && screenshot) {
    printError('--url and --screenshot are mutually exclusive -- pass exactly one.', json);
    return 2;
  }
  if (!url && !screenshot) {
    printError('One of --url or --screenshot is required.', json);
    return 2;
  }

  let sources: RuleSource[];
  try {
    sources = buildSources(rubric);
  } catch (err) {
    if (err instanceof RubricLoadError) {
      printError(err.message, json);
      return 2;
    }
    printError(`Unexpected error while initializing scoring sources: ${(err as Error).message}`, json);
    return 2;
  }

  const target = url ?? screenshot ?? '';

  try {
    const result = await scoreComposite(sources, { url, screenshotPath: screenshot });
    printReport(result, target, rubric, json);

    if (failBelow !== undefined && result.compositeScore < failBelow) {
      return 1;
    }
    return 0;
  } catch (err) {
    if (err instanceof MissingApiKeyError) {
      printError(err.message, json);
      return 2;
    }
    printError(`slop-eval failed to score "${target}": ${(err as Error).message}`, json);
    return 2;
  }
}

/** Builds the commander program. Exported so tests can inspect --help output without invoking process.exit. */
export function buildProgram(): Command {
  const program = new Command();

  program
    .name('slop-eval')
    .description(
      'Scores AI-generated UI for genericness ("slop") using an LLM-judge rubric. ' +
        'This is a heuristic quality signal, not a certification -- see the score subcommand for details.',
    )
    .version('0.1.0');

  program
    .command('score')
    .description(
      'Score a URL or screenshot for AI-UI genericness against a versioned rubric.\n\n' +
        'Note on --url mode (v0.1 limitation): this tool does not bundle a headless ' +
        'browser. If --url is given, the raw HTML/text response is fetched and given ' +
        'to the judge as a fallback input, instead of a rendered screenshot -- the judge ' +
        'can reason about markup and copy, but not the actual visual layout. For the ' +
        'stronger, layout-aware signal, render the page yourself and pass --screenshot.',
    )
    .option('--url <url>', 'URL to score (fetched as raw HTML/text -- see limitation note above)')
    .option('--screenshot <path>', 'path to a screenshot image to score (preferred over --url)')
    .option('--rubric <name>', 'rubric version to use, reads src/rubric/<name>.json', 'v1')
    .option('--json', 'output structured JSON instead of a human-readable report', false)
    .option(
      '--fail-below <n>',
      'exit code 1 if the composite score is below this threshold (0-100); no threshold by default',
      (value: string) => {
        const parsed = Number(value);
        if (Number.isNaN(parsed)) {
          throw new Error(`--fail-below must be a number, got "${value}"`);
        }
        return parsed;
      },
    )
    .action(async (opts: { url?: string; screenshot?: string; rubric: string; json: boolean; failBelow?: number }) => {
      const exitCode = await runScore({
        url: opts.url,
        screenshot: opts.screenshot,
        rubric: opts.rubric,
        json: opts.json,
        failBelow: opts.failBelow,
      });
      process.exitCode = exitCode;
    });

  return program;
}

/* istanbul ignore next -- exercised via the built dist/cli.js in manual verification, not unit tests */
if (require.main === module) {
  const program = buildProgram();
  program.parseAsync(process.argv).catch((err) => {
    // eslint-disable-next-line no-console -- last-resort handler for errors commander itself couldn't route (e.g. bad --fail-below parse)
    console.error(`Error: ${(err as Error).message}`);
    process.exitCode = 2;
  });
}
