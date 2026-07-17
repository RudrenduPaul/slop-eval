#!/usr/bin/env python3
"""
01 -- basic score.

The simplest possible use of the slop_eval library: build the two v0.1
RuleSources, call score_composite() against a real screenshot, and read
back composite_score / findings. Scores the repo's own test fixture
(../../tests/fixtures/sample.png), so it runs standalone with no setup
beyond `pip install -e .` (or `pip install slop-eval-cli`) from the
python/ directory -- plus a live ANTHROPIC_API_KEY for the LLM-judge
portion (get one at https://console.anthropic.com/).

Without a key set, this script does not crash or fabricate a score: it
catches MissingApiKeyError, prints the same actionable message the CLI
itself would print, and still reports the one source that needs no key
(ScreenshotDiffSource's honest "not scored" stub), so the composable
RuleSource design is visible either way.

Run:
    export ANTHROPIC_API_KEY="sk-ant-..."   # optional -- see docstring above
    python3 examples/01-basic-score/score.py
"""
from pathlib import Path

from slop_eval import (
    LLMJudgeSource,
    MissingApiKeyError,
    ScoreInput,
    ScreenshotDiffSource,
    score_composite,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SCREENSHOT = REPO_ROOT / "tests" / "fixtures" / "sample.png"


def main() -> None:
    score_input = ScoreInput(screenshot_path=str(FIXTURE_SCREENSHOT))

    try:
        sources = [LLMJudgeSource("v1"), ScreenshotDiffSource()]
        result = score_composite(sources, score_input)
    except MissingApiKeyError as err:
        print(str(err))
        print()
        print("Falling back to the one source that needs no API key:")
        result = score_composite([ScreenshotDiffSource()], score_input)

    print(f"Target:          {FIXTURE_SCREENSHOT}")
    print(f"Composite score: {round(result.composite_score)}/100")
    print()
    for finding in result.findings:
        print(f"[{finding.status}] {finding.category}: {finding.score}/10")
        print(f"  {finding.evidence}")
        print()


if __name__ == "__main__":
    main()
