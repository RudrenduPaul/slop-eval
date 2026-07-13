# Contributing to slop-eval

## Setup

```bash
npm install
npm run build
npm test
```

All four must pass before a PR is reviewed: `npm run build` (TypeScript compiles clean), `npm run lint`, `npm test` (coverage stays at or above the thresholds below), `npm audit --audit-level=high` (no high/critical vulnerabilities).

## Coverage requirements

80% minimum overall. 95%+ on `src/scorer/composite.ts` and `src/sources/LLMJudgeSource.ts` -- these two modules directly produce the CI-gate verdict, so a bug there is a wrong CI decision, not just a wrong test.

## The highest-leverage contribution: a new RuleSource

The `RuleSource` interface (`src/sources/RuleSource.ts`) exists so a new detection method -- a different LLM provider, a deterministic rule catalog adapter, a corpus-backed diff -- can be added without touching the composite scorer. If you're adding a new signal, implement `RuleSource`, add fixture-backed unit tests (never call a real external API or LLM in tests -- mock the client), and wire it in wherever `LLMJudgeSource`/`ScreenshotDiffSource` are currently instantiated.

## Never do this

- Claim a detection/scoring number without a test-fixture command output backing it.
- Ship a new `RuleSource` without unit tests against fixture inputs.
- Add a real network call (LLM API, HTTP fetch) inside the test suite -- mock it.
- Claim slop-eval is "the first" tool in this space (Impeccable's Slop catalog and aislop already exist -- see the README's comparison table).
- Claim TTHW or speed parity with Impeccable or aislop -- they're deterministic and near-instant; slop-eval's LLM-judge call is honestly slower, and the README states that tradeoff plainly.

## Reporting a bug

Open a GitHub issue with the exact command you ran, the `--json` output if you have it, and (if the finding is about scoring accuracy) the screenshot or URL that produced the unexpected score. "The rubric got this wrong" reports are especially useful -- they're how the rubric improves.
