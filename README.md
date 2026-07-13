# slop-eval

Score AI-generated UI for genericness using an LLM judge, so a CI check can catch the same "this looks like every other AI-built app" problem a human reviewer would flag on sight.

```bash
npx slop-eval-cli score --screenshot ./preview.png
```

## Why this exists, and what it isn't

Nutlope's Hallmark (a popular AI design skill, 3.5k+ stars) has an open issue where a user says flatly: "all of it looks like slop." The maintainer closed it `NOT_PLANNED`. Separately, Hallmark's own maintainer opened a PR titled "Add eval-driven quality harness for Hallmark outputs" that sat unmerged for over a month. Both are real and dated as of this writing. Neither is proof that demand for a harness is large, only that the gap is real and currently unaddressed.

slop-eval is not the first tool to touch this space, and it does not try to be. Two real, free tools already exist nearby:

- **[Impeccable's Slop catalog](https://impeccable.style/slop/)** ships a deterministic, no-LLM CLI that checks 37-44 specific visual tells of AI-generated UI (gradient palettes, glassmorphism, side-stripe borders, WCAG contrast violations). It's fast because it never calls a model.
- **[aislop](https://github.com/scanaislop/aislop)** does the same kind of deterministic, rule-based scoring for AI-generated *code* (not UI), positioned exactly as a CI quality gate.

Neither does holistic, judgment-based scoring: "does this layout feel novel," "does this component choice feel considered," the kind of read a rule can't easily encode. That's the gap slop-eval fills, and it's built to compose with tools like Impeccable's, not replace them.

## What it does

```bash
$ slop-eval score --screenshot ./preview.png

slop-eval v0.1 -- AI-Slop Quality Score
Target: ./preview.png

Score: 62/100

[FLAG]  Layout novelty: 4/10
  Matches a common hero + 3-card grid + footer CTA pattern.

[PASS]  Component-pattern novelty: 7/10
  Custom data-table interaction not typical of generated scaffolds.

[NOT SCORED] Screenshot-diff-vs-corpus
  v0.1 has no labeled corpus yet -- ships once real usage produces one (see Roadmap).

Summary: 1 pass, 1 flagged, 1 not scored
```

Every flag names the specific reason, not just a number -- a score with no evidence isn't actionable, and isn't what this tool is for.

## Honest comparison

| | slop-eval | Impeccable (Slop) | aislop |
|---|---|---|---|
| Target | AI-generated **UI** | AI-generated **UI** | AI-generated **code** |
| Detection method | LLM judge (holistic) | Deterministic rules (37-44 checks) | Deterministic rules (50+ checks) |
| Requires an API key | Yes (BYO Anthropic key) | No | No |
| Speed | Slower by design -- a real model call is in the critical path | Near-instant, no network call | Sub-second, no network call |
| Composable rule sources | Yes -- `RuleSource` plugin interface | No (fixed rule set) | No (fixed rule set) |
| License | Apache 2.0 | Free (license not Apache-verified here -- check their repo) | MIT |
| CI-gate model | GitHub Action, `--fail-below` threshold | Not primarily a CI product | Yes, CI quality gate |

If you want fast, deterministic, zero-cost checks for known AI-UI tells, Impeccable's tool is the better fit today. If you want a holistic judgment call on layout and component novelty that a fixed rule set can't easily encode, that's what slop-eval adds. Nothing stops you from running both in the same CI job.

**On speed:** slop-eval is genuinely slower than Impeccable and aislop, because an LLM call is in the critical path. v0.1's real, measured CLI-overhead numbers (this repo, 2026-07-13, `--help` and error paths, no scoring call):

| Command | Real measured time |
|---|---|
| `slop-eval score --help` | 0.49s |
| `slop-eval score --url <x>` (no API key, fails fast) | 0.26s |
| `slop-eval score --screenshot <x>` (no API key, fails fast) | 0.19s |

The actual scored-run latency (a real LLM-judge call, fresh vs. cached) is a **target, not yet a measured result**: under 10 seconds fresh, under 1 second on a cache hit for identical input (the content-hash cache in `src/cache/judge-cache.ts` guarantees the second number -- the first is an estimate pending a real run with a live API key). We'll update this table with real numbers once that run happens; we would rather say "not yet measured" than assert a number we can't reproduce.

## Install

```bash
npm install -g slop-eval-cli
# or run without installing:
npx slop-eval-cli score --screenshot ./preview.png
```

Requires `ANTHROPIC_API_KEY` in your environment (bring your own key -- this is not a hosted service, and no key is ever sent anywhere but Anthropic's API). Get one at [console.anthropic.com](https://console.anthropic.com/).

## CLI reference

```
slop-eval score [options]

Options:
  --url <url>          URL to score (fetched as raw HTML/text -- v0.1 does not
                        render pages; see limitation below)
  --screenshot <path>  path to a screenshot image to score (preferred over --url)
  --rubric <name>      rubric version to use (default: "v1")
  --json               output structured JSON instead of a human-readable report
  --fail-below <n>     exit code 1 if the composite score is below this
                        threshold (0-100); no threshold by default
```

Exit codes: `0` success (no threshold, or score at/above `--fail-below`), `1` success but below threshold, `2` usage error or unrecoverable failure (missing API key, unreadable file, malformed rubric).

**`--url` limitation (v0.1, by design):** this tool doesn't bundle a headless browser. `--url` fetches the raw HTML/text response and hands it to the judge as a text fallback -- the judge can reason about markup and copy, not the actual rendered visual layout. `--screenshot` is the stronger signal; render the page yourself (Playwright, Puppeteer, or your CI's existing preview-screenshot step) and pass the image.

## GitHub Action

```yaml
- uses: RudrenduPaul/slop-eval/action@main
  with:
    url: ${{ steps.deploy.outputs.preview_url }}
    fail-below: 50
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Posts a PR comment leading with the most specific flagged finding (not just the composite number) -- see `action/README.md` for the full input reference.

## The rubric is public and versioned

Every score is graded against `src/rubric/v1.json` -- a real, versioned, inspectable file, not a black box. Read it, propose changes, or pin a specific version with `--rubric`. Re-scoring history under a new rubric version is always an explicit action (`slop-eval rescore --rubric v2`, planned for v0.2), never silent, so a rubric change never quietly rewrites a historical score.

## What a score means (and doesn't)

A slop-eval score is a heuristic quality signal from one LLM's read of your UI against a stated rubric. It is not a certification that something is or isn't AI-generated, and a clean score doesn't mean the UI is good by every measure -- only that this rubric, at this version, didn't flag it.

## Roadmap

- **v0.1 (this release):** LLM-judge scoring, CLI, GitHub Action, content-hash caching.
- **v0.2:** `ScreenshotDiffSource` becomes real (currently a documented stub -- no labeled corpus exists yet; fabricating one before real usage produces genuine examples would be worse than shipping without it). An Impeccable-catalog adapter, pending a license check.

## Contributing

Issues and PRs welcome -- see `CONTRIBUTING.md`. New `RuleSource` implementations are the highest-leverage contribution: the plugin interface exists specifically so a new detection method doesn't require touching the composite scorer.

## License

Apache 2.0. See `LICENSE`.
