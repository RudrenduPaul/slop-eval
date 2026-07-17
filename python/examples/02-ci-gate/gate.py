#!/usr/bin/env python3
"""
02 -- CI gate.

Demonstrates using score_composite() as an actual CI gate script: takes a
screenshot path and a --fail-below-style threshold from the command line
(falling back to the repo's own test fixture and a threshold of 50 so it's
runnable with zero arguments), prints a summary, and returns a real process
exit code -- exactly what you'd drop into a CI pipeline step (see
../../docs/integrations/ci.md for the GitHub Actions version of this same
pattern). Same exit-code contract as the CLI's --fail-below flag: 0 pass,
1 below threshold, 2 error (including a missing ANTHROPIC_API_KEY).

Run:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 examples/02-ci-gate/gate.py
    python3 examples/02-ci-gate/gate.py ../../tests/fixtures/sample.png 80
"""
import sys
from pathlib import Path

from slop_eval import (
    LLMJudgeSource,
    MissingApiKeyError,
    ScoreInput,
    ScreenshotDiffSource,
    score_composite,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCREENSHOT = REPO_ROOT / "tests" / "fixtures" / "sample.png"


def main() -> int:
    screenshot = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_SCREENSHOT)
    fail_below = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0

    try:
        sources = [LLMJudgeSource("v1"), ScreenshotDiffSource()]
        result = score_composite(sources, ScoreInput(screenshot_path=screenshot))
    except MissingApiKeyError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    except Exception as err:  # noqa: BLE001 -- mirrors the CLI's own top-level scoring guard
        print(f'ERROR: slop-eval failed to score "{screenshot}": {err}', file=sys.stderr)
        return 2

    score = round(result.composite_score)
    if score >= fail_below:
        print(f"PASS: {screenshot} scored {score}/100 (threshold {fail_below}).")
        return 0

    print(f"FAIL: {screenshot} scored {score}/100, below the {fail_below} threshold:", file=sys.stderr)
    for finding in result.findings:
        if finding.status == "flag":
            print(f"  [{finding.status}] {finding.category}: {finding.score}/10 -- {finding.evidence}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
