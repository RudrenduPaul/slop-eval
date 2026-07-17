# slop-eval

Score AI-generated UI for genericness with an LLM judge, so a CI check catches the same "this looks like every other AI-built app" problem a human reviewer would flag on sight.

[![CI](https://github.com/RudrenduPaul/slop-eval/actions/workflows/ci.yml/badge.svg)](https://github.com/RudrenduPaul/slop-eval/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE)
[![Node](https://img.shields.io/badge/node-%3E%3D18-brightgreen.svg)](./package.json)

```bash
slop-eval score --screenshot ./preview.png --json
```

## Two distributions: npm (live) and Python (publish in progress)

`slop-eval-cli` is live on npm -- `npx slop-eval-cli score ...` works today (see [Quickstart](#quickstart) below). A genuine Python port also ships in this repo under [`python/`](./python/) (`pip install slop-eval-cli`, package `slop_eval`), built and tested (56/56 tests) against the same rubric and Anthropic judge prompt. Its first PyPI publish is in progress -- this notice will drop the moment `pip install slop-eval-cli` is live. See [`python/README.md`](./python/README.md) for Python-specific usage in the meantime.

## Why this exists, and what it isn't

Nutlope's Hallmark, a popular AI design skill with 3.5k+ stars, has an open issue where a user says flatly: "all of it looks like slop." The maintainer closed it `NOT_PLANNED`. Separately, Hallmark's own maintainer opened a PR titled "Add eval-driven quality harness for Hallmark outputs" that sat unmerged for over a month. Both are real and dated as of this writing. Neither proves the demand is large, only that the gap is real and currently unaddressed.

slop-eval is not the first tool in this space, and it doesn't try to be. Two real, free tools already sit nearby:

- **[Impeccable's Slop catalog](https://impeccable.style/slop/)** ships a CLI that flags 46 specific visual tells of AI-generated UI (gradient palettes, glassmorphism, side-stripe borders, WCAG contrast violations). 41 of those 46 checks run as deterministic rules with no model call; a separate `impeccable critique` command adds an opt-in LLM review pass. Core detection stays fast because it doesn't need a model for most of its checks.
- **[aislop](https://github.com/scanaislop/aislop)** does the deterministic, rule-based equivalent for AI-generated *code* (not UI): 50+ regex/AST rules across 8 languages, no LLM in the runtime path, positioned exactly as a CI quality gate.

Neither does holistic, judgment-based UI scoring: "does this layout feel novel," "does this component choice feel considered," the kind of read a fixed rule can't easily encode. That's the gap slop-eval fills, built to compose with tools like Impeccable's rather than replace them.

## Features

Verified against the code in this repo, not aspirational:

- **Three rubric categories, each with mandatory cited evidence.** `src/rubric/v1.json` scores layout novelty, visual-identity distinctiveness, and component-pattern novelty, 0-10 each. A finding with no specific citation is treated as a bug, not a valid score (see `src/sources/RuleSource.ts`).
- **LLM judge via forced tool-call, returning structured JSON.** `LLMJudgeSource` calls the Anthropic API with `tool_choice` locked to a `submit_slop_scores` schema: the response comes back as reliably structured JSON instead of a chat reply that has to be regexed apart.
- **`--json` mode for CI and agents.** Every run can emit a parseable `{ target, rubric, compositeScore, findings[], summary, disclaimer }` object on stdout, on both success and error paths, so a script or agent never has to branch on shape to find an error string.
- **Real exit-code contract.** `0` success (no threshold, or score at/above `--fail-below`), `1` success but below threshold, `2` usage error or unrecoverable failure. Verified directly this session; see [CLI reference](#cli-reference).
- **Content-hash caching.** `src/cache/judge-cache.ts` hashes the input bytes and skips the API call entirely on a repeat run against unchanged input, a correctness guarantee (an unchanged PR can't flap a CI gate from LLM run-to-run variance), not just a cost saver.
- **Composable `RuleSource` plugin interface.** `src/sources/RuleSource.ts` is the boundary every scoring source implements. Today that's one real source (`LLMJudgeSource`) and one documented stub (`ScreenshotDiffSource`, honestly reported as `not_scored` until a real labeled corpus exists), so a future rule catalog or a second LLM provider slots in without touching the composite scorer.
- **Screenshot input (real visual read) or `--url` fallback.** `--screenshot` sends the actual rendered image to the judge. `--url` is a documented v0.1 limitation: no bundled headless browser, so it fetches raw HTML/text and the judge reasons over markup and copy instead of layout.
- **GitHub Action that leads with the specific flag, then the score.** `action/action.yml` posts a PR comment headed by the single most specific flagged finding, followed by the composite score, giving a reviewer the reasoning behind the number.
- **Versioned, public rubric.** Every score names the rubric version (`v1` today) that produced it. Rubric changes ship as a new file, never a silent edit to an existing one.

## Quickstart

Requires Node.js 18+ and an `ANTHROPIC_API_KEY` (BYO key; get one at [console.anthropic.com](https://console.anthropic.com/)).

```bash
git clone https://github.com/RudrenduPaul/slop-eval.git
cd slop-eval
npm install
npm run build

export ANTHROPIC_API_KEY="sk-ant-..."
./dist/cli.js score --screenshot ./test/fixtures/sample.png
```

For CI or agent consumption, add `--json`:

```bash
./dist/cli.js score --screenshot ./test/fixtures/sample.png --json
```

```json
{
  "target": "./test/fixtures/sample.png",
  "rubric": "v1",
  "compositeScore": 62,
  "findings": [
    {
      "ruleId": "llm-judge.layout-novelty",
      "category": "Layout novelty",
      "score": 4,
      "evidence": "Matches a common hero + 3-card grid + footer CTA pattern.",
      "status": "flag"
    }
  ],
  "summary": { "pass": 1, "flagged": 1, "notScored": 1 },
  "disclaimer": "This score is a heuristic quality signal from an LLM judge, not a certification..."
}
```

Without a key set, every run (human or `--json`) fails fast with exit code 2 and a clear "set `ANTHROPIC_API_KEY`" message, verified directly against the built CLI this session:

```bash
./dist/cli.js score --screenshot ./test/fixtures/sample.png --json
# {"error":"ANTHROPIC_API_KEY environment variable is not set.\n..."}
# exit code 2
```

## CLI reference

```
slop-eval score [options]

Options:
  --url <url>          URL to score (fetched as raw HTML/text -- v0.1 does not
                        render pages; see limitation below)
  --screenshot <path>  path to a screenshot image to score (preferred over --url)
  --rubric <name>       rubric version to use (default: "v1")
  --json                output structured JSON instead of a human-readable report
  --fail-below <n>      exit code 1 if the composite score is below this
                        threshold (0-100); no threshold by default
```

Exit codes: `0` success (no threshold, or score at/above `--fail-below`), `1` success but below threshold, `2` usage error or unrecoverable failure (missing API key, unreadable file, malformed rubric, mutually exclusive `--url`/`--screenshot`).

`--url` and `--screenshot` are mutually exclusive; passing both or neither is a usage error (exit 2) in either output mode.

**`--url` limitation (v0.1, by design):** no bundled headless browser. `--url` fetches raw HTML/text and hands it to the judge as a text fallback, reasoning over markup and copy rather than the rendered layout. `--screenshot` is the stronger signal; render the page yourself (Playwright, Puppeteer, or your CI's existing preview-screenshot step) and pass the image.

## GitHub Action

```yaml
- uses: RudrenduPaul/slop-eval/action@main
  with:
    url: ${{ steps.deploy.outputs.preview_url }}
    fail-below: 50
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Posts a PR comment leading with the most specific flagged finding, then the composite score. Full input/output reference in `action/README.md`.

## Honest comparison

| | slop-eval | Impeccable (Slop) | aislop |
|---|---|---|---|
| Target | AI-generated **UI** | AI-generated **UI** | AI-generated **code** |
| Detection method | LLM judge (holistic) | Deterministic rules, 41 of 46 checks; separate `critique` command adds LLM review | Deterministic rules (50+ checks) |
| Requires an API key | Yes (BYO Anthropic key) | No, for the core 41 deterministic checks | No |
| Speed | Slower by design, a real model call is in the critical path | Near-instant for the deterministic checks | Sub-second, no network call |
| Composable rule sources | Yes, `RuleSource` plugin interface | No (fixed rule set) | No (fixed rule set) |
| License | Apache 2.0 | Not stated on the product page as of this check | MIT |
| CI-gate model | GitHub Action, `--fail-below` threshold | Not primarily positioned as a CI product | Yes, CI quality gate |

Want fast, deterministic, zero-cost checks for known AI-UI tells? Impeccable's tool is the better fit today. For a holistic judgment call on layout and component novelty that a fixed rule set can't easily encode, that's what slop-eval adds. Nothing stops you from running both in the same CI job.

**On speed:** slop-eval is genuinely slower than Impeccable's core checks and aislop, because an LLM call sits in the critical path. Real, measured CLI-overhead numbers from this repo (`--help` and error paths, no scoring call):

| Command | Real measured time |
|---|---|
| `slop-eval score --help` | 0.49s |
| `slop-eval score --url <x>` (no API key, fails fast) | 0.26s |
| `slop-eval score --screenshot <x>` (no API key, fails fast) | 0.19s |

The actual scored-run latency (a real LLM-judge call, fresh vs. cached) is a **target, not yet a measured result** in this environment, since it requires a live `ANTHROPIC_API_KEY`: under 10 seconds fresh, under 1 second on a cache hit for identical input (the content-hash cache in `src/cache/judge-cache.ts` guarantees the second number; the first is an estimate pending a real run with a live key). We would rather say "not yet measured" than assert a number we can't reproduce.

## What a score means (and doesn't)

A slop-eval score is a heuristic quality signal from one LLM's read of your UI against a stated rubric. It is not a certification that something is or isn't AI-generated, and a clean score doesn't mean the UI is good by every measure, only that this rubric, at this version, didn't flag it.

## The rubric is public and versioned

Every score is graded against `src/rubric/v1.json`, a real, versioned, inspectable file, not a black box. Read it, propose changes, or pin a specific version with `--rubric`. A rubric version is never edited in place; a change ships as a new file so a historical score always records which rubric produced it.

## FAQ

**Does this replace Impeccable's Slop catalog or aislop?** No. It targets a different signal (holistic layout/component judgment vs. fixed visual-tell rules) and is built to run alongside them in the same CI job.

**Do I need an API key?** Yes. slop-eval is bring-your-own-key against the Anthropic API; there's no shared or hosted key. Nothing is sent anywhere except Anthropic's API.

**Can I use a different model provider (OpenAI, Gemini)?** Not in v0.1. `LLMJudgeSource` calls the Anthropic API directly; `ANTHROPIC_MODEL` only lets you pick a different Anthropic model. A pluggable provider is a natural fit for the `RuleSource` interface later, but it isn't built yet, so don't take "composable rule sources" to mean "multi-provider" today.

**Does `--url` render the page like a browser would?** No, not in v0.1. It fetches the raw HTML/text response and hands that to the judge as a fallback. Render the page yourself and pass `--screenshot` for a real visual read.

**Will re-running slop-eval on the same PR flap the CI check?** No. Identical input (same screenshot bytes, or same URL plus fetched content) hits the content-hash cache in `src/cache/judge-cache.ts` and never re-calls the API, so the same input always returns the same cached result.

**Is `screenshot-diff-vs-corpus` a real check today?** No. It's a real `RuleSource` implementation in the code, but v0.1 ships it as an honest `not_scored` stub because no labeled comparison corpus exists yet. Hand-seeding an unvalidated corpus would be a less honest signal than reporting "not scored." Corpus-backed diffing is planned for v0.2.

## Roadmap

- **v0.1 (this release):** LLM-judge scoring, CLI, GitHub Action, content-hash caching, `--json` mode.
- **v0.2:** `ScreenshotDiffSource` becomes real once a genuine labeled corpus exists. An Impeccable-catalog adapter, pending a license check. Explicit `rescore --rubric v2` command so a rubric bump is never silent.

## Security

`ANTHROPIC_API_KEY` is read from the environment only, is never logged, and is never written to the content-hash cache -- see `SECURITY.md` for the full policy and the private disclosure process.

## Contributing

Issues and PRs welcome, see `CONTRIBUTING.md` (covers both the npm and Python packages). New `RuleSource` implementations are the highest-leverage contribution: the plugin interface exists specifically so a new detection method doesn't require touching the composite scorer.

## License

Apache 2.0. See `LICENSE`.
