# CLAUDE.md -- slop-eval

## Project Identity

- **Idea:** Open, model-agnostic CI eval harness that scores AI-generated UI for
  genericness ("slop") using an LLM-judge rubric, built as a composable pipeline
  (RuleSource plugin interface) that complements deterministic rule catalogs like
  Impeccable's Slop rather than re-inventing them -- free/OSS CLI + rubric, plus a
  paid hosted CI quality-gate dashboard for teams
- **Repo:** RudrenduPaul/slop-eval
- **npm package:** slop-eval-cli (bin: `slop-eval`)
- **Distribution:** npx slop-eval-cli / npm install -g slop-eval-cli, plus a
  GitHub Action wrapper for CI-triggered scoring
- **Language:** Node/TypeScript
- **License:** Apache 2.0 (core scorer, rubric/corpus data, CLI, GitHub Action) +
  proprietary (hosted CI dashboard, historical trends, team thresholds -- not in
  this repo)
- **Known competitors (do not duplicate their work, complement it):** Impeccable's
  Slop catalog (impeccable.style/slop -- free, deterministic, no-LLM, 37-44 UI-tell
  rules) and scanaislop/aislop (MIT, deterministic, code-quality CI gate). slop-eval's
  actual differentiation is the LLM-judge holistic layer neither of them ships --
  never claim to be "the first" tool in this space.
- **Repo goal:** Become the reference LLM-judge scoring layer for AI-generated-UI
  quality, composable with deterministic rule catalogs -- NOT a competitor to
  app-builders (Lovable, Magic Patterns, 21st.dev) and NOT a rewrite of Impeccable's
  or aislop's rule catalogs.

## Git Workflow

When asked to commit, push, or "update GitHub" -- just do it. No questions.

- `git add` relevant files -> `git commit` -> `git push origin main` in one shot
- Never use `Co-Authored-By:` lines.

## Engineering Standards (block all tasks until these pass)

1. **Lint:** project's configured linter (eslint), zero errors
2. **Typecheck/build:** `tsc --noEmit` and build, zero errors
3. **Tests:** 80% minimum overall; 95%+ on `src/scorer/composite.ts` and
   `src/sources/LLMJudgeSource.ts` (the modules that directly produce the CI-gate
   verdict -- a bug there is a wrong CI decision)
4. **Security:** `npm audit --audit-level=high` -- no HIGH or CRITICAL unfixed
   vulnerabilities in the dependency tree
5. **Judge-cache correctness:** every change to `src/cache/judge-cache.ts` or
   `src/sources/LLMJudgeSource.ts` must re-run the cache-hit-count test (same
   content-hash input never triggers a second LLM call) before merge

Do NOT mark a task complete if any of these fail. Fix the root cause. Do not
suppress errors or add `// eslint-disable` without a comment explaining why.

## Anti-Sycophancy Rules

These override default behavior in every session:

1. **No detection-accuracy, scoring, or benchmark claim without a labeled fixture
   run.** Show the command output before stating a number in code, docs, or README.
2. **Every flagged rubric category must cite the exact criterion and evidence**
   that drove the flag -- a score with no explanation is not shippable (this is the
   "magical moment" per the devex review; a bare number is not).
3. **Never claim a score means "not AI-generated" or "definitely slop."** State
   plainly in every generated report that this is a heuristic quality signal, not
   a certification.
4. **Comparison claims require specificity.** Any comparison to Impeccable,
   aislop, Hallmark, Lovable, Magic Patterns, or 21st.dev must state exactly what
   differs -- never "we do this too."
5. **Never state the fundraising/investor-outreach motive anywhere in this repo.**
   Not in the README, code comments, commit messages, or CONTRIBUTING docs.
6. **Never claim TTHW or speed parity with Impeccable/aislop.** They are
   deterministic and near-instant; slop-eval's LLM-judge call is honestly slower
   (<10s fresh, <1s cached per the devex review) -- state the tradeoff, don't hide it.

## What Claude Must Never Do

- Claim a detection/scoring number without a test-fixture command output
- Ship a new RuleSource without a unit test against fixture inputs
- Commit with `--no-verify`
- Merge a PR that regresses coverage below the stated thresholds without explicit
  written approval
- State that a score is a certification of "not AI slop"
- Claim to be "the first" AI-UI-quality-scoring tool (Impeccable and aislop exist)
- State the fundraising/investor-outreach motive anywhere in this repo

## Key Files

| File | Purpose |
|---|---|
| `src/cli.ts` | CLI entry point -- `score` command, `--url`/`--screenshot`/`--rubric`/`--json` flags |
| `src/sources/RuleSource.ts` | Plugin interface every rule source implements |
| `src/sources/LLMJudgeSource.ts` | First-party LLM-judge implementation, content-hash cached |
| `src/sources/ScreenshotDiffSource.ts` | v0.1: interface + stub only (no corpus yet, see eng-review) |
| `src/sources/impeccable-adapter.ts` | v0.1-or-v0.2, gated on license check -- do not build until cleared |
| `src/scorer/composite.ts` | Combines RuleSource[] outputs into one composite score + breakdown |
| `src/cache/judge-cache.ts` | Content-hash -> cached LLM-judge score |
| `src/report/writer.ts` | JSON + human-readable terminal report writer |
| `action/` | GitHub Action wrapper (composite action calling the CLI) |
| `test/fixtures/` | Test screenshots/URLs, source of every published detection/scoring claim |
| `CONTRIBUTING.md` | Read before any contributor-facing change |
| `CHANGELOG.md` | Updated on every PR that changes public behavior |

## Session Start Checklist

1. Run `git status` and `git log --oneline -5` to understand current state
2. Run the test suite to confirm baseline is green before touching anything
3. Read the full execution plan at the source strategy repo (session-plan,
   office-hours design doc, CEO review, eng review -- all under
   `research-strategy-slop-eval/strategy-execution/` in the
   `oss-ideas-execution-strategy` repo) before making an architecture change
4. Check whether Impeccable's Slop catalog license has been cleared for the
   `impeccable-adapter.ts` integration -- if not, do not build it yet
