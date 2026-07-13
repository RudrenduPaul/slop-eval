# slop-eval GitHub Action

Runs [`slop-eval-cli`](https://github.com/RudrenduPaul/slop-eval) against a URL (e.g. a CI preview deploy) and posts a PR comment leading with the single most specific flagged finding, plus the composite score.

Requires an `ANTHROPIC_API_KEY` secret in the calling repo -- slop-eval is BYO-key; there is no shared or default key.

## Usage

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

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `url` | yes | -- | URL to score. v0.1 fetches raw HTML/text (no headless-browser rendering) -- see the CLI's `--help` for the same limitation. |
| `fail-below` | no | (none) | Fail the check if the composite score is below this 0-100 threshold. Leave unset to always pass and only report. |
| `rubric` | no | `v1` | Rubric version to score against. |
| `github-token` | no | `${{ github.token }}` | Token used to post the PR comment. |

## Outputs

| Output | Description |
|---|---|
| `composite-score` | The composite 0-100 slop-eval score. |

## Notes

- The PR comment is only posted on `pull_request` events (it needs `context.issue.number`).
- This is a heuristic quality signal from an LLM judge, not a certification -- see slop-eval's own disclaimer in every report.
- The fresh (uncached) LLM-judge call is honestly slower than a deterministic rule catalog like Impeccable's Slop or aislop -- budget for it in CI timing, don't expect sub-second results on a cache miss.
