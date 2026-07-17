# Getting started

slop-eval scores AI-generated UI for genericness ("slop") using an
Anthropic LLM-judge rubric. It ships as two independent, equally
first-class packages: an npm package (`slop-eval-cli`, JavaScript/
TypeScript) and a PyPI package (`slop-eval-cli`, Python). Both score
against the same versioned rubric and call the Anthropic API with the same
forced-tool-call judge prompt. Pick whichever fits your toolchain, or
install both.

## Install

**npm (JS/TS CLI + GitHub Action):**

```bash
npm install -g slop-eval-cli
# or run it once without installing:
npx slop-eval-cli score --screenshot ./preview.png
```

**pip (Python library + CLI):**

```bash
pip install slop-eval-cli
```

Both packages are BYO-key: you supply your own `ANTHROPIC_API_KEY`. Get one
at [console.anthropic.com](https://console.anthropic.com/). Neither package
bundles a shared or default key.

## Your first score

```bash
export ANTHROPIC_API_KEY="sk-ant-..."

# npm CLI
npx slop-eval-cli score --screenshot ./preview.png

# Python CLI (after `pip install slop-eval-cli`)
slop-eval score --screenshot ./preview.png
```

Both print a human-readable report by default. The example below
illustrates the report's shape (it is not a captured live run -- no
Anthropic API key was available while writing this documentation; the
real numbers and evidence text come from whatever your screenshot and the
live judge actually produce):

```
slop-eval v0.1 -- AI-Slop Quality Score (rubric: v1)
Target: ./preview.png

Score: 62/100

[FLAG]  Layout novelty: 4/10
  Matches a common hero + 3-card grid + footer CTA pattern.

[PASS]  Visual-identity distinctiveness: 8/10
  Custom color palette and iconography, no generic AI-tell gradient.

[NOT SCORED] screenshot-diff-vs-corpus
  slop-eval v0.1 ships this RuleSource as an interface only -- there is no
  seeded comparison corpus yet...

Summary: 1 pass, 1 flagged, 1 not scored

This score is a heuristic quality signal from an LLM judge, not a
certification. It does not mean the UI "is" or "is not" AI-generated, and
it is not a guarantee of quality in either direction.
```

Add `--json` for machine-parseable output on both success and error paths:

```bash
slop-eval score --screenshot ./preview.png --json
```

Exit codes (identical contract on both CLIs): `0` success (no
`--fail-below` threshold, or score at/above it), `1` success but below
`--fail-below`, `2` usage error or unrecoverable failure (missing API key,
unreadable file, malformed rubric, `--url`/`--screenshot` both or neither
given).

## Using the library instead of the CLI

**Python:** the Python package exports a programmatic scoring API from its
top-level `slop_eval` module, for an agent framework that wants to call
slop-eval in-process instead of shelling out to a CLI binary:

```python
from slop_eval import LLMJudgeSource, ScreenshotDiffSource, ScoreInput, score_composite

sources = [LLMJudgeSource("v1"), ScreenshotDiffSource()]
result = score_composite(sources, ScoreInput(screenshot_path="./preview.png"))
print(result.composite_score, result.findings)
```

The result carries `composite_score`, and `findings` (each with `rule_id`,
`category`, `score`, `evidence`, `status`) -- see [concepts.md](./concepts.md)
for the full data model and rubric.

**TypeScript:** the npm package's documented, supported public surface is
the CLI (`slop-eval score ...`) and the GitHub Action -- its `package.json`
`main` entry points at the compiled CLI script, and the repo does not ship
a documented library/barrel export for `LLMJudgeSource`, `scoreComposite`,
etc. If you need slop-eval's scoring logic in-process from a Node/TypeScript
agent today, shell out to the CLI with `--json` and parse stdout (see
[integrations/ci.md](./integrations/ci.md)) rather than assuming a deep
import path into `dist/`, since that surface isn't part of the package's
stated contract and could change without notice.

## Next steps

- [concepts.md](./concepts.md) -- what the rubric actually scores, how the
  composite score is computed, and the `RuleSource` plugin architecture.
- [integrations/ci.md](./integrations/ci.md) -- wiring slop-eval into a CI
  pipeline (the npm package's bundled GitHub Action, and a plain CI step
  for the Python CLI).
- The [examples/](../examples/) directory for runnable scripts against the
  real Python library API.
- The [project README](https://github.com/RudrenduPaul/slop-eval#readme)
  for the full comparison against Impeccable's Slop catalog and aislop.
