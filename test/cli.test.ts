import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as path from 'path';
import { runScore, buildProgram, handleParseError, isJsonModeRequested } from '../src/cli';
import { LLMJudgeSource } from '../src/sources/LLMJudgeSource';
import type { RuleSource, RuleFinding } from '../src/sources/RuleSource';

const FIXTURE_PNG = path.join(__dirname, 'fixtures', 'sample.png');

function fakeSources(findings: RuleFinding[]): RuleSource[] {
  return [{ name: 'fake', score: async () => findings }];
}

describe('runScore (CLI `score` command)', () => {
  let logSpy: ReturnType<typeof vi.spyOn>;
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    logSpy = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    logSpy.mockRestore();
    errorSpy.mockRestore();
  });

  it('exits 2 when neither --url nor --screenshot is given (usage error)', async () => {
    const code = await runScore({ url: undefined, screenshot: undefined, rubric: 'v1', json: false });
    expect(code).toBe(2);
    expect(errorSpy).toHaveBeenCalled();
  });

  it('exits 2 when both --url and --screenshot are given (mutually exclusive)', async () => {
    const code = await runScore({ url: 'https://x.example', screenshot: 'a.png', rubric: 'v1', json: false });
    expect(code).toBe(2);
  });

  it('emits valid JSON (not human text) for the usage error when --json is passed', async () => {
    const code = await runScore({ url: undefined, screenshot: undefined, rubric: 'v1', json: true });
    expect(code).toBe(2);
    const output = logSpy.mock.calls[0][0] as string;
    const parsed = JSON.parse(output);
    expect(parsed).toHaveProperty('error');
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('exits 0 with no --fail-below threshold regardless of how low the score is', async () => {
    const code = await runScore(
      { url: 'https://example.com', rubric: 'v1', json: true },
      () => fakeSources([{ ruleId: 'a', category: 'A', score: 1, evidence: 'e', status: 'flag' }]),
    );
    expect(code).toBe(0);
  });

  it('exits 1 when the composite score is below --fail-below', async () => {
    const code = await runScore(
      { url: 'https://example.com', rubric: 'v1', json: true, failBelow: 90 },
      () => fakeSources([{ ruleId: 'a', category: 'A', score: 1, evidence: 'e', status: 'flag' }]),
    );
    expect(code).toBe(1);
  });

  it('exits 0 when the composite score meets --fail-below', async () => {
    const code = await runScore(
      { url: 'https://example.com', rubric: 'v1', json: true, failBelow: 50 },
      () => fakeSources([{ ruleId: 'a', category: 'A', score: 9, evidence: 'e', status: 'pass' }]),
    );
    expect(code).toBe(0);
  });

  it('emits the documented JSON schema on a successful --json run', async () => {
    await runScore(
      { url: 'https://example.com', rubric: 'v1', json: true },
      () => fakeSources([{ ruleId: 'a', category: 'A', score: 9, evidence: 'e', status: 'pass' }]),
    );

    const output = logSpy.mock.calls[0][0] as string;
    const parsed = JSON.parse(output);
    expect(parsed).toHaveProperty('target', 'https://example.com');
    expect(parsed).toHaveProperty('rubric', 'v1');
    expect(parsed).toHaveProperty('compositeScore');
    expect(parsed).toHaveProperty('findings');
    expect(parsed).toHaveProperty('summary');
    expect(parsed).toHaveProperty('disclaimer');
  });

  it('prints a human-readable report (not JSON) when --json is not passed', async () => {
    await runScore(
      { screenshot: FIXTURE_PNG, rubric: 'v1', json: false },
      () => fakeSources([{ ruleId: 'a', category: 'A', score: 9, evidence: 'specific evidence text', status: 'pass' }]),
    );

    const output = logSpy.mock.calls[0][0] as string;
    expect(() => JSON.parse(output)).toThrow();
    expect(output).toContain('slop-eval v0.1');
    expect(output).toContain('specific evidence text');
  });

  it('exits 2 with a clear, JSON-valid error when ANTHROPIC_API_KEY is missing (real LLMJudgeSource, no network call)', async () => {
    const originalKey = process.env.ANTHROPIC_API_KEY;
    delete process.env.ANTHROPIC_API_KEY;

    const code = await runScore(
      { screenshot: FIXTURE_PNG, rubric: 'v1', json: true },
      (rubric) => [new LLMJudgeSource(rubric)],
    );

    expect(code).toBe(2);
    const output = logSpy.mock.calls[0][0] as string;
    const parsed = JSON.parse(output);
    expect(parsed).toHaveProperty('error');
    expect(parsed.error).toMatch(/ANTHROPIC_API_KEY/);

    if (originalKey === undefined) delete process.env.ANTHROPIC_API_KEY;
    else process.env.ANTHROPIC_API_KEY = originalKey;
  });

  it('exits 2 with a clear message when the requested rubric does not exist', async () => {
    const code = await runScore(
      { url: 'https://example.com', rubric: 'does-not-exist', json: false },
      (rubric) => [new LLMJudgeSource(rubric)],
    );

    expect(code).toBe(2);
    expect(errorSpy.mock.calls[0][0]).toMatch(/[Rr]ubric/);
  });

  it('exits 2 with a clear error for an unreadable screenshot path (real LLMJudgeSource, fails before any API call)', async () => {
    const code = await runScore(
      { screenshot: '/nonexistent/path/nope.png', rubric: 'v1', json: false },
      (rubric) => [new LLMJudgeSource(rubric)],
    );
    expect(code).toBe(2);
    expect(errorSpy.mock.calls[0][0]).toMatch(/Could not read screenshot/);
  });

  it('uses the default (real) source builder when no override is passed, failing fast on an unreadable screenshot without any network call', async () => {
    const code = await runScore({ screenshot: '/nonexistent/path/nope.png', rubric: 'v1', json: false });
    expect(code).toBe(2);
    expect(errorSpy.mock.calls[0][0]).toMatch(/Could not read screenshot/);
  });

  it('exits 2 with a clear message when buildSources throws a non-rubric error', async () => {
    const code = await runScore(
      { url: 'https://example.com', rubric: 'v1', json: false },
      () => {
        throw new Error('boom -- unexpected init failure');
      },
    );
    expect(code).toBe(2);
    expect(errorSpy.mock.calls[0][0]).toMatch(/Unexpected error while initializing/);
  });
});

describe('buildProgram (`slop-eval score --help` shape)', () => {
  it('exposes a score subcommand with the documented flags', () => {
    const program = buildProgram();
    const scoreCmd = program.commands.find((c) => c.name() === 'score');

    expect(scoreCmd).toBeDefined();
    const flags = scoreCmd!.options.map((o) => o.long);
    expect(flags).toEqual(
      expect.arrayContaining(['--url', '--screenshot', '--rubric', '--json', '--fail-below']),
    );
  });

  it('documents the --url v0.1 fallback limitation in the score subcommand description', () => {
    const program = buildProgram();
    const scoreCmd = program.commands.find((c) => c.name() === 'score');
    expect(scoreCmd!.description()).toMatch(/headless browser/i);
  });

  it('--fail-below custom parser accepts a valid number and rejects a non-numeric value', () => {
    const program = buildProgram();
    const scoreCmd = program.commands.find((c) => c.name() === 'score')!;
    const failBelowOption = scoreCmd.options.find((o) => o.long === '--fail-below')!;
    // Commander stores the custom coercion function as parseArg.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const parseArg = (failBelowOption as any).parseArg as (value: string, previous: unknown) => number;

    expect(parseArg('42', undefined)).toBe(42);
    expect(() => parseArg('not-a-number', undefined)).toThrow(/--fail-below must be a number/);
  });

  it('isJsonModeRequested detects --json anywhere in argv, regardless of flag order', () => {
    expect(isJsonModeRequested(['node', 'cli.js', 'score', '--json', '--fail-below', 'x'])).toBe(true);
    expect(isJsonModeRequested(['node', 'cli.js', 'score', '--fail-below', 'x', '--json'])).toBe(true);
    expect(isJsonModeRequested(['node', 'cli.js', 'score', '--fail-below', 'x'])).toBe(false);
  });

  it('handleParseError emits valid JSON (regression: bad --fail-below with --json must not leak plain text) when --json is present in argv', () => {
    const localLogSpy = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const localErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    try {
      const code = handleParseError(
        new Error('--fail-below must be a number, got "notanumber"'),
        ['node', 'cli.js', 'score', '--json', '--screenshot', 'a.png', '--fail-below', 'notanumber'],
      );
      expect(code).toBe(2);
      expect(localLogSpy).toHaveBeenCalledTimes(1);
      const output = localLogSpy.mock.calls[0][0] as string;
      const parsed = JSON.parse(output);
      expect(parsed).toEqual({ error: '--fail-below must be a number, got "notanumber"' });
      expect(localErrorSpy).not.toHaveBeenCalled();
    } finally {
      localLogSpy.mockRestore();
      localErrorSpy.mockRestore();
    }
  });

  it('handleParseError emits human-readable text (not JSON) when --json is absent from argv', () => {
    const localLogSpy = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const localErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    try {
      const code = handleParseError(
        new Error('--fail-below must be a number, got "notanumber"'),
        ['node', 'cli.js', 'score', '--screenshot', 'a.png', '--fail-below', 'notanumber'],
      );
      expect(code).toBe(2);
      expect(localErrorSpy).toHaveBeenCalledWith('Error: --fail-below must be a number, got "notanumber"');
      expect(localLogSpy).not.toHaveBeenCalled();
    } finally {
      localLogSpy.mockRestore();
      localErrorSpy.mockRestore();
    }
  });

  it('the score subcommand action handler runs end-to-end via parseAsync and sets process.exitCode', async () => {
    const program = buildProgram();
    const originalExitCode = process.exitCode;
    process.exitCode = undefined;

    try {
      await program.parseAsync(['score', '--screenshot', '/nonexistent/path/nope.png'], { from: 'user' });
      expect(process.exitCode).toBe(2);
    } finally {
      process.exitCode = originalExitCode;
    }
  });
});
