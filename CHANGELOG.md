# Changelog

All notable changes to slop-eval are documented in this file. This
changelog covers both distributions -- the npm package (`slop-eval-cli`,
JS/TS) and the PyPI package (`slop-eval-cli`, Python) -- since they score
against the same versioned rubric (`v1`) and the same Anthropic
forced-tool-call judge prompt; entries note which distribution they apply
to.

## [Python 0.1.0] - 2026-07-16

Initial public release of the Python port, published to PyPI as
`slop-eval-cli` (`pip install slop-eval-cli`). Complementary to, not a
replacement for, the existing npm package -- both are first-class and
maintained together. See `python/README.md` for Python-specific usage.

### Added

- `slop-eval score` CLI (console script `slop-eval`, package `slop_eval`)
  with the same flags as the npm CLI: `--url`, `--screenshot`, `--rubric`
  (default `v1`), `--json`, `--fail-below`. Same exit-code contract (`0`
  pass, `1` below threshold, `2` usage/unrecoverable error).
- Programmatic library API: `from slop_eval import score_composite,
  ScoreInput, LLMJudgeSource, ScreenshotDiffSource`, returning the same
  structured result shape (`CompositeResult` with `composite_score` and
  `findings`).
- `LLMJudgeSource`, calling the Anthropic API through the official
  `anthropic` Python SDK with the same forced `submit_slop_scores`
  tool-call pattern, the same `v1` rubric (`src/slop_eval/rubric/v1.json`,
  ported byte-for-byte), and the same judge prompt wording as the
  TypeScript original.
- `ScreenshotDiffSource`, the same documented v0.1 stub (always one
  `not_scored` finding, no seeded corpus yet) as the TypeScript original.
- Content-hash judge cache (`slop_eval/cache.py`), same correctness
  guarantee as the TypeScript original: identical input never triggers a
  second API call.
- The `RuleSource` plugin interface (`slop_eval/sources/base.py`), the
  same composable boundary the TypeScript original defines.
- Full pytest suite (56 tests) ported from the TypeScript vitest suite,
  covering the composite scorer, the judge cache, the rubric loader, the
  LLM-judge source (Anthropic API fully mocked, no real network call in
  any test), the report writer, the screenshot-diff stub, and the CLI.

### Notes

- **One documented behavioral difference from the TypeScript original:**
  the TypeScript `scoreComposite()` runs every `RuleSource` concurrently
  via `Promise.all`; the Python port runs them sequentially in list order.
  With exactly two v0.1 sources, the result (same findings, same order,
  same composite score) is identical either way.
- **No bundled GitHub Action for the Python distribution.** The npm
  package's `action/action.yml` wraps the Node CLI specifically; the
  Python distribution documents an equivalent plain CI step instead (see
  `python/docs/integrations/ci.md`).
- **Live Anthropic API testing was not possible while building this
  release** -- no `ANTHROPIC_API_KEY` was available in the build
  environment. Every test mocks the Anthropic client; the CLI's
  no-API-key error path (exit code 2, JSON-safe) and `--help` output were
  verified directly against the built package. A real scored run (fresh
  vs. cached LLM-judge latency) has not been measured for this release,
  same honest caveat the npm package's own README states for its
  numbers.

## [0.1.0] - 2026-07-15

Initial release of the npm package (`slop-eval-cli`, TypeScript).

### Added

- `slop-eval score` CLI (`--url`, `--screenshot`, `--rubric`, `--json`,
  `--fail-below`) with a real exit-code contract (`0`/`1`/`2`).
- `LLMJudgeSource`: Anthropic API judge via a forced `submit_slop_scores`
  tool call, scoring against the versioned `v1` rubric
  (`src/rubric/v1.json`): layout novelty, visual-identity
  distinctiveness, component-pattern novelty.
- `ScreenshotDiffSource`: documented v0.1 stub, honestly reports
  `not_scored` (no seeded comparison corpus exists yet).
- Content-hash judge cache (`src/cache/judge-cache.ts`): identical input
  never re-triggers an API call.
- Composable `RuleSource` plugin interface (`src/sources/RuleSource.ts`).
- GitHub Action (`action/action.yml`) that scores a URL and posts a PR
  comment leading with the single most specific flagged finding.
