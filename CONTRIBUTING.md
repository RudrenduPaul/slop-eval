# Contributing to slop-eval

slop-eval ships two independently maintained, equally first-class
distributions: an npm package (`slop-eval-cli`, TypeScript, repo root) and
a PyPI package (`slop-eval-cli`, Python, `python/`). Both score against the
same versioned rubric (`src/rubric/v1.json` and `python/src/slop_eval/rubric/v1.json`,
kept identical by hand since they're separate language runtimes) and call
the Anthropic API with the same forced-tool-call judge prompt. Which
section below applies depends on which codebase you're touching.

## Ground rules (both codebases)

- Every change lands with tests. Neither test suite is optional scaffolding.
- A rubric change (a new/edited category, a changed judge instruction) must
  be made in **both** `src/rubric/v1.json` (TypeScript) and
  `python/src/slop_eval/rubric/v1.json` (Python) -- or, if the change is
  substantial, ship as a new versioned rubric file in both places rather
  than editing `v1.json` in place. A rubric that only exists for one
  language is a silent behavior gap between the two CLIs.
- No real network call to the Anthropic API (or any other external
  service) inside either test suite -- mock the client.
- Never claim a detection/scoring number without a real command's output
  backing it.

## Working on the TypeScript package (repo root)

```bash
npm install
npm run build
npm test
```

All four must pass before a PR is reviewed: `npm run build` (TypeScript compiles clean), `npm run lint`, `npm test` (coverage stays at or above the thresholds below), `npm audit --audit-level=high` (no high/critical vulnerabilities).

### Coverage requirements

80% minimum overall. 95%+ on `src/scorer/composite.ts` and `src/sources/LLMJudgeSource.ts` -- these two modules directly produce the CI-gate verdict, so a bug there is a wrong CI decision, not just a wrong test.

## Working on the Python package (`python/`)

```bash
cd python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

- Source lives under `python/src/slop_eval/`, laid out to mirror the
  TypeScript module structure (`sources/` for `LLMJudgeSource`/
  `ScreenshotDiffSource`/`RuleSource`, `scorer.py`, `cache.py`,
  `report.py`, `cli.py`, `errors.py`) so a change in one codebase has an
  obvious counterpart to check in the other.
- The rubric (`python/src/slop_eval/rubric/v1.json`) ships inside the
  wheel, loaded via `importlib.resources` rather than a repo-relative
  filesystem path (a pip-installed wheel has no source checkout to resolve
  against).
- Tests use `pytest` (`python/tests/test_*.py`); the Anthropic client is
  always mocked (see `tests/test_llm_judge_source.py`'s `FakeAnthropic`).
- There is no enforced minimum coverage threshold today; the bar is that
  the full suite passes and new behavior ships with tests.
- One intentional divergence from the TypeScript original: `score_composite()`
  runs sources sequentially rather than via `Promise.all`-style
  concurrency (Python's synchronous `anthropic` client and stdlib
  `urllib` don't need Node's async I/O model for this). Keep this in mind
  if you're diffing behavior between the two CLIs -- the *result* (same
  findings, same order, same composite score) is identical; only the
  execution model differs.
- Build and verify a real install before opening a PR that touches
  packaging (build the venv *outside* `python/` so it's never accidentally
  bundled into the sdist):
  ```bash
  python3 -m venv /tmp/slop-eval-verify
  /tmp/slop-eval-verify/bin/python3 -m build python --outdir /tmp/slop-eval-verify/dist
  /tmp/slop-eval-verify/bin/pip install /tmp/slop-eval-verify/dist/*.whl
  /tmp/slop-eval-verify/bin/slop-eval score --help
  ```

## The highest-leverage contribution: a new RuleSource

The `RuleSource` interface (`src/sources/RuleSource.ts` / `python/src/slop_eval/sources/base.py`)
exists so a new detection method -- a different LLM provider, a
deterministic rule catalog adapter, a corpus-backed diff -- can be added
without touching the composite scorer, in either language. If you're
adding a new signal, implement `RuleSource`, add fixture-backed unit tests
(never call a real external API or LLM in tests -- mock the client), and
wire it in wherever `LLMJudgeSource`/`ScreenshotDiffSource` are currently
instantiated. See `python/examples/03-agent-native-json/agent_report.py`
for a minimal real example on the Python side.

## Never do this

- Claim a detection/scoring number without a test-fixture command output backing it.
- Ship a new `RuleSource` without unit tests against fixture inputs.
- Add a real network call (LLM API, HTTP fetch) inside the test suite -- mock it.
- Claim slop-eval is "the first" tool in this space (Impeccable's Slop catalog and aislop already exist -- see the README's comparison table).
- Claim TTHW or speed parity with Impeccable or aislop -- they're deterministic and near-instant; slop-eval's LLM-judge call is honestly slower, and the README states that tradeoff plainly.

## Reporting a bug

Open a GitHub issue with the exact command you ran, the `--json` output if you have it, and (if the finding is about scoring accuracy) the screenshot or URL that produced the unexpected score. "The rubric got this wrong" reports are especially useful -- they're how the rubric improves.
