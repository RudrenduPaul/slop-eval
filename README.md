# slop-eval

slop-eval scores AI-generated UI for genericness ("slop") using an LLM-judge rubric, shipped as a composable `RuleSource` plugin pipeline so it can complement deterministic rule catalogs (like Impeccable's Slop or aislop) rather than compete with them. This is a heuristic quality signal, not a certification.

## Install

```bash
npm install -g slop-eval-cli
# or run without installing:
npx slop-eval-cli score --url https://your-preview-deploy.example.com
```

Requires a bring-your-own `ANTHROPIC_API_KEY` environment variable -- see `slop-eval score --help` for details.

A full benchmarked README (comparisons, real fixture-backed metrics) lands in a later pipeline step.
