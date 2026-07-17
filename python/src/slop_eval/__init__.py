"""
Programmatic / agent-native entry point.

    from slop_eval import score_composite, ScoreInput, LLMJudgeSource, ScreenshotDiffSource

    sources = [LLMJudgeSource("v1"), ScreenshotDiffSource()]
    result = score_composite(sources, ScoreInput(screenshot_path="./preview.png"))
    print(result.composite_score, result.findings)

Returns the same structured CompositeResult the CLI formats for human/json
output -- an agent framework can call this in-process instead of shelling
out to the CLI.

This is the Python port of the slop-eval-cli npm package
(https://www.npmjs.com/package/slop-eval-cli). Both distributions score
against the same versioned rubric (see slop_eval/rubric/v1.json) and call
the Anthropic API with the same forced-tool-call judge prompt; see
https://github.com/RudrenduPaul/slop-eval for the canonical documentation
and the original TypeScript source.
"""
from .errors import MissingApiKeyError, RubricLoadError
from .report import build_json_report, print_error, print_report, render_human_report
from .scorer import CompositeResult, score_composite
from .sources.base import RuleFinding, RuleFindingStatus, RuleSource, ScoreInput
from .sources.llm_judge import LLMJudgeSource, Rubric, RubricCategory, load_rubric
from .sources.screenshot_diff import ScreenshotDiffSource

__version__ = "0.1.0"

__all__ = [
    "score_composite",
    "CompositeResult",
    "RuleFinding",
    "RuleFindingStatus",
    "RuleSource",
    "ScoreInput",
    "LLMJudgeSource",
    "ScreenshotDiffSource",
    "Rubric",
    "RubricCategory",
    "load_rubric",
    "build_json_report",
    "render_human_report",
    "print_report",
    "print_error",
    "MissingApiKeyError",
    "RubricLoadError",
    "__version__",
]
