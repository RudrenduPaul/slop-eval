# Python examples

Each numbered subdirectory is a real, runnable script against the actual
`slop_eval` Python library (`from slop_eval import score_composite, ...`),
not pseudocode. Two of the three examples (`02-ci-gate`, part of
`01-basic-score`) call the real Anthropic API through `LLMJudgeSource` and
need a live `ANTHROPIC_API_KEY` to actually score something; every script
detects a missing key and exits with the same clear, actionable error the
CLI itself produces, rather than crashing or faking a result. `03-agent-native-json`
is fully runnable with no API key at all -- it demonstrates the
`RuleSource` plugin interface with a small custom source that needs no
network call.

Install the package first (editable install from this checkout, or `pip
install slop-eval-cli` from PyPI both work identically):

```bash
cd python
pip install -e .
```

Then run any example directly:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # required for 01 and 02; 03 works without it
python3 examples/01-basic-score/score.py
python3 examples/02-ci-gate/gate.py
python3 examples/03-agent-native-json/agent_report.py
```

| Example | What it demonstrates |
| --- | --- |
| [01-basic-score](./01-basic-score/) | The core library call: `score_composite()` against a real screenshot, reading back `composite_score`/`findings`, printing a human-readable summary. Requires `ANTHROPIC_API_KEY` for the LLM-judge portion; falls back to reporting just the `ScreenshotDiffSource` stub finding if the key is unset. |
| [02-ci-gate](./02-ci-gate/) | Using `score_composite()` as a CI gate: a `--fail-below`-style threshold, real process exit-code propagation, suitable to drop into a CI script directly. Requires `ANTHROPIC_API_KEY`. |
| [03-agent-native-json](./03-agent-native-json/) | The agent-native use case: building the same JSON schema the CLI's `--json` mode emits, and implementing a minimal custom `RuleSource` to show the composable plugin architecture. Runs with no API key required. |
