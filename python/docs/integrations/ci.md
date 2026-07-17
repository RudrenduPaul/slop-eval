# CI integrations

slop-eval is meant to run as a quality-gate check on a CI preview deploy or
a rendered screenshot artifact. Both packages support the same
`--json`/`--fail-below` contract, so pick whichever matches your pipeline's
existing toolchain. Both require an `ANTHROPIC_API_KEY` secret in the
calling repo -- slop-eval is BYO-key; there is no shared or default key.

## GitHub Actions -- npm CLI, bundled composite Action

The `slop-eval` repo ships a composite GitHub Action (`action/action.yml`)
that wraps the npm CLI and posts a PR comment leading with the single most
specific flagged finding:

```yaml
name: slop-eval
on:
  pull_request:

jobs:
  slop-eval:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: RudrenduPaul/slop-eval/action@main
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        with:
          url: https://my-preview-deploy.example.com
          fail-below: '50'
```

Full input/output reference in the action's own
[README](https://github.com/RudrenduPaul/slop-eval/blob/main/action/README.md).

## GitHub Actions -- Python CLI, plain step

The Python package has no bundled composite Action; the equivalent
pipeline is a few lines using the real `slop-eval` console script:

```yaml
name: slop-eval (Python)
on: [pull_request]

jobs:
  slop-eval-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install slop-eval-cli
      - name: Score the preview deploy
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          slop-eval score --url "$PREVIEW_URL" --json --fail-below 50 > slop-eval-result.json
          cat slop-eval-result.json
        env:
          PREVIEW_URL: ${{ steps.deploy.outputs.preview_url }}
```

`--fail-below` alone gives you real exit-code gating (`1` on a
below-threshold score): the step above fails the job automatically without
any extra `if` logic, the same exit-code contract the npm CLI's Action uses
internally.

## Calling the library directly (no subprocess)

For an agent framework or a custom CI script already running Python, call
`score_composite()` in-process instead of shelling out -- see
[examples/02-ci-gate](../../examples/02-ci-gate/) for a full runnable
version of this pattern:

```python
import sys
from slop_eval import LLMJudgeSource, ScreenshotDiffSource, ScoreInput, score_composite

result = score_composite(
    [LLMJudgeSource("v1"), ScreenshotDiffSource()],
    ScoreInput(url="https://my-preview-deploy.example.com"),
)

if round(result.composite_score) < 50:
    print(f"slop-eval score {round(result.composite_score)}/100 is below threshold", file=sys.stderr)
    sys.exit(1)
```

## Choosing a --fail-below threshold

There is no single "correct" threshold -- it depends on how strict a gate
you want. Leaving `--fail-below` unset means slop-eval always exits `0`
(unless it errors) and only reports; the score becomes a visible signal in
the PR/CI log without ever blocking a merge. Setting a threshold turns it
into a real gate. Since `--url` mode is a documented v0.1 fallback (raw
HTML/text, not a rendered screenshot -- see
[concepts.md](../concepts.md#how-the-llm-judge-is-called)), a `--url`-based
gate is judging markup and copy, not visual layout; render the page
yourself and pass `--screenshot` for the stronger, layout-aware signal
before trusting a strict threshold.
