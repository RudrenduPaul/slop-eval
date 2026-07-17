# slop-eval-cli (Python)

Score AI-generated UI for genericness with an Anthropic LLM judge, so a CI
check catches the same "this looks like every other AI-built app" problem a
human reviewer would flag on sight.

[![PyPI version](https://img.shields.io/pypi/v/slop-eval-cli.svg)](https://pypi.org/project/slop-eval-cli/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/RudrenduPaul/slop-eval/blob/main/LICENSE)
[![Python versions](https://img.shields.io/pypi/pyversions/slop-eval-cli.svg)](https://pypi.org/project/slop-eval-cli/)
[![npm version](https://img.shields.io/npm/v/slop-eval-cli.svg)](https://www.npmjs.com/package/slop-eval-cli)

## Why this exists

slop-eval scores a screenshot (or, as a fallback, a URL's raw HTML/text)
against a versioned, public rubric using the Anthropic API, called with a
forced tool call so the response comes back as structured JSON instead of a
chat reply that has to be parsed apart. It complements deterministic
AI-UI-tell catalogs (Impeccable's Slop, aislop) rather than replacing them:
neither of those does holistic, judgment-based scoring ("does this layout
feel novel," "does this component choice feel considered") the way an LLM
judge can. Full background and the honest comparison table live in the
[project README](https://github.com/RudrenduPaul/slop-eval#readme).

This package is the Python distribution -- a genuine, independent port of
the npm package's scoring logic, not a wrapper around the Node binary. It
calls the Anthropic API directly via the official `anthropic` Python SDK.

## Install

```bash
pip install slop-eval-cli
```

or with [uv](https://docs.astral.sh/uv/):

```bash
uv add slop-eval-cli
```

The complementary JS/TS distribution installs the same way on the npm side:
`npm install -g slop-eval-cli` (or `npx slop-eval-cli score ...` to run it
once without installing) -- see the
[project README](https://github.com/RudrenduPaul/slop-eval#readme) for that
package. Both are first-class, maintained together; neither is deprecated
in favor of the other.

## Quickstart

Requires Python 3.9+ and an `ANTHROPIC_API_KEY` (BYO key; get one at
[console.anthropic.com](https://console.anthropic.com/)).

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
slop-eval score --screenshot ./preview.png
```

For CI or agent consumption, add `--json`:

```bash
slop-eval score --screenshot ./preview.png --json
```

Illustrative shape of the output (not a captured live run -- no Anthropic
API key was available in the environment this package was built in; the
real score and evidence text come from whatever your screenshot and the
live judge actually produce):

```json
{
  "target": "./preview.png",
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

Without a key set, every run (human or `--json`) fails fast with exit code
2 and a clear "set `ANTHROPIC_API_KEY`" message:

```bash
slop-eval score --screenshot ./preview.png --json
# {"error": "ANTHROPIC_API_KEY environment variable is not set.\n..."}
# exit code 2
```

Or call the library directly (the agent-native path):

```python
from slop_eval import score_composite, ScoreInput, LLMJudgeSource, ScreenshotDiffSource

sources = [LLMJudgeSource("v1"), ScreenshotDiffSource()]
result = score_composite(sources, ScoreInput(screenshot_path="./preview.png"))

print(f"Composite score: {round(result.composite_score)}/100")
for finding in result.findings:
    print(f"[{finding.status}] {finding.category}: {finding.score}/10 -- {finding.evidence}")
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

Exit codes: `0` success (no threshold, or score at/above `--fail-below`), `1`
success but below threshold, `2` usage error or unrecoverable failure
(missing API key, unreadable file, malformed rubric, mutually exclusive
`--url`/`--screenshot`). Identical contract to the npm CLI.

`--url` and `--screenshot` are mutually exclusive; passing both or neither
is a usage error (exit 2) in either output mode.

**`--url` limitation (v0.1, by design):** no bundled headless browser.
`--url` fetches raw HTML/text via the Python standard library's `urllib`
and hands it to the judge as a text fallback, reasoning over markup and
copy rather than the rendered layout. `--screenshot` is the stronger
signal; render the page yourself (Playwright, Puppeteer, or your CI's
existing preview-screenshot step) and pass the image.

## Real measured CLI overhead

Measured directly against the built `slop-eval` console script in this
package (no scoring call -- `--help` and the no-API-key error path, which
both exit before any network I/O):

| Command | Real measured time |
| --- | --- |
| `slop-eval score --help` | 0.67s |
| `slop-eval score --url <x>` (no API key, fails fast, exit 2) | 0.71s |
| `slop-eval score --screenshot <x>` (no API key, fails fast, exit 2) | 0.52s |

These are consistently slower than the npm CLI's own documented numbers for
the same three commands (0.49s, 0.26s, 0.19s) -- Python process startup
plus importing the `anthropic` SDK's dependency tree costs more per
invocation than Node's. Like the npm package's own README states for its
numbers: the actual scored-run latency (a real LLM-judge call, fresh vs.
cached) is a target, not a measured result in this environment, since it
requires a live `ANTHROPIC_API_KEY` this environment does not have; the
content-hash cache in `src/slop_eval/cache.py` guarantees a cache hit skips
the API call entirely, but the number for a fresh call is not asserted here
without having actually run one.

## How this port works

```
--url / --screenshot
     |
     v
LLMJudgeSource            ScreenshotDiffSource (v0.1 stub,
(Anthropic API,             always "not_scored" --
content-hash cached)        no corpus yet)
     |                           |
     +-------------+-------------+
                    v
          composite scorer (average of
          non-"not_scored" 0-10 scores,
          scaled to 0-100)
                    v
          report writer (human text or --json)
```

- **Same rubric, same prompt.** `src/slop_eval/rubric/v1.json` is the same
  three-category rubric (layout novelty, visual-identity distinctiveness,
  component-pattern novelty) the npm package scores against, and the judge
  prompt/instructions text in `src/slop_eval/sources/llm_judge.py` is a
  direct port of the TypeScript original's wording.
- **Anthropic API via the official SDK.** `LLMJudgeSource` calls
  `anthropic.Anthropic().messages.create(...)` with `tool_choice` locked to
  a `submit_slop_scores` tool, the same forced-tool-call pattern the npm
  package uses, instead of reimplementing raw HTTP calls.
- **Content-hash caching.** `src/slop_eval/cache.py` hashes the input bytes
  (screenshot bytes, or URL + fetched text) and skips the API call on a
  repeat run against unchanged input -- a correctness guarantee, not just a
  cost saver, ported from the same reasoning in the TypeScript original's
  judge-cache.
- **Composable `RuleSource` interface.** `src/slop_eval/sources/base.py`
  defines the same plugin boundary (`name` + `score()`) the npm package
  uses, so a future rule catalog adapter or second LLM provider can slot in
  without touching the composite scorer.
- **One documented difference:** the TypeScript original runs its
  `RuleSource`s concurrently via `Promise.all` (Node's I/O model is
  naturally async). This Python port runs them sequentially in list order.
  With exactly two v0.1 sources, the result (same findings, same order,
  same composite score) is identical either way -- sequential is simply the
  simpler implementation for that source count.

## What a score means (and doesn't)

A slop-eval score is a heuristic quality signal from one LLM's read of your
UI against a stated rubric. It is not a certification that something is or
isn't AI-generated, and a clean score doesn't mean the UI is good by every
measure, only that this rubric, at this version, didn't flag it. The same
disclaimer is embedded in every report this CLI prints.

## CI integration

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with:
    python-version: '3.12'
- run: pip install slop-eval-cli
- run: slop-eval score --url "$PREVIEW_URL" --json --fail-below 50 > slop-eval-result.json
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Full walkthrough in
[docs/integrations/ci.md](https://github.com/RudrenduPaul/slop-eval/blob/main/python/docs/integrations/ci.md).
The npm package additionally ships a ready-made composite GitHub Action
(`uses: RudrenduPaul/slop-eval/action@main`) that wraps the Node CLI and
posts a PR comment; the Python distribution has no equivalent bundled
Action today (a plain CI step, as above, is the current path).

## Security

slop-eval's whole job is calling an external LLM with user-supplied
content (a screenshot or fetched page text) -- it never `eval()`s or
`exec()`s anything read from a scan target, and the only network calls it
makes are to the Anthropic API (`--screenshot` mode) or the one URL you
pass it (`--url` mode). `ANTHROPIC_API_KEY` is read from the environment
only, is never logged, and is never sent anywhere except the Anthropic API
via the official `anthropic` SDK's own transport. See
[SECURITY.md](https://github.com/RudrenduPaul/slop-eval/blob/main/SECURITY.md)
for the full policy and the private disclosure process. **Honest note:**
this project does not currently publish SLSA provenance, Sigstore
signatures, or an SBOM, and has no OpenSSF Scorecard badge -- none of that
infrastructure exists yet for either distribution, so it isn't claimed
here.

## Contributing

See [CONTRIBUTING.md](https://github.com/RudrenduPaul/slop-eval/blob/main/CONTRIBUTING.md).
There is no enforced minimum coverage threshold for the Python package
today; the bar is that the full pytest suite (`pytest` from `python/`)
passes and new behavior ships with tests, mocking the Anthropic API rather
than calling it for real.

```bash
cd python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0, see [LICENSE](https://github.com/RudrenduPaul/slop-eval/blob/main/LICENSE).
