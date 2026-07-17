#!/usr/bin/env python3
"""
slop-eval CLI entry point. Ported from src/cli.ts, using the stdlib
`argparse` in place of the TypeScript original's `commander` dependency, to
avoid a CLI-framework dependency (the same design choice the skillguard-cli
Python port made over commander/yargs equivalents).

Subcommand: `score` -- scores a URL or screenshot for AI-UI genericness
("slop") using the LLM-judge rubric, plus the (v0.1 stub) screenshot-diff
source.

Exit codes (identical contract to the npm CLI):
  0 -- ran successfully, and either no --fail-below threshold was given or
       the composite score met it.
  1 -- ran successfully, but the composite score is below --fail-below.
  2 -- usage/input error (bad flags, missing required input) or an
       unrecoverable error (missing API key, unreadable file, malformed
       rubric).

`--json` mode always emits valid JSON on stdout, on both success and error
paths, so an agent invoking this CLI programmatically gets a consistent,
parseable schema either way.

Design note vs. the TypeScript original: commander's custom `--fail-below`
coercion can throw *during argument parsing*, before the JSON-vs-human
output mode is known -- src/cli.ts works around this with a
handleParseError()/isJsonModeRequested() pair that inspects raw argv.
This port sidesteps the issue structurally: --fail-below is accepted as a
plain string by argparse and validated inside run_score() itself, which
already knows the requested output mode from the parsed --json flag, so
every validated error path (bad --fail-below, missing/conflicting
url/screenshot, bad rubric, missing API key) honors --json consistently
with no separate raw-argv inspection needed.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional

from .errors import MissingApiKeyError, RubricLoadError
from .report import print_error, print_report
from .scorer import score_composite
from .sources.base import RuleSource, ScoreInput
from .sources.llm_judge import LLMJudgeSource
from .sources.screenshot_diff import ScreenshotDiffSource

_VERSION = "0.1.0"

_SCORE_DESCRIPTION = (
    "Score a URL or screenshot for AI-UI genericness against a versioned rubric.\n\n"
    "Note on --url mode (v0.1 limitation): this tool does not bundle a headless "
    "browser. If --url is given, the raw HTML/text response is fetched and given "
    "to the judge as a fallback input, instead of a rendered screenshot -- the judge "
    "can reason about markup and copy, but not the actual visual layout. For the "
    "stronger, layout-aware signal, render the page yourself and pass --screenshot."
)


@dataclass
class ScoreOptions:
    url: Optional[str] = None
    screenshot: Optional[str] = None
    rubric: str = "v1"
    json: bool = False
    fail_below: Optional[str] = None
    """Raw string as received from the CLI; parsed to a number inside run_score()."""


def _default_build_sources(rubric: str) -> List[RuleSource]:
    return [LLMJudgeSource(rubric), ScreenshotDiffSource()]


def run_score(
    options: ScoreOptions,
    build_sources: Optional[Callable[[str], List[RuleSource]]] = None,
) -> int:
    """
    Runs the `score` command end-to-end and returns the process exit code.
    Callers (including the CLI's own main()) print through this function
    rather than calling sys.exit directly, so tests can invoke it in-process
    and assert on the returned code plus captured stdout.

    :param build_sources: overridable for tests that need to inject a fake
        RuleSource list instead of constructing the real LLMJudgeSource
        (which requires ANTHROPIC_API_KEY). Defaults to the real sources.
    """
    if build_sources is None:
        build_sources = _default_build_sources

    url, screenshot, json_mode = options.url, options.screenshot, options.json

    if url and screenshot:
        print_error("--url and --screenshot are mutually exclusive -- pass exactly one.", json_mode)
        return 2
    if not url and not screenshot:
        print_error("One of --url or --screenshot is required.", json_mode)
        return 2

    fail_below: Optional[float] = None
    if options.fail_below is not None:
        try:
            fail_below = float(options.fail_below)
        except ValueError:
            print_error(f'--fail-below must be a number, got "{options.fail_below}"', json_mode)
            return 2

    try:
        sources = build_sources(options.rubric)
    except RubricLoadError as err:
        print_error(str(err), json_mode)
        return 2
    except Exception as err:  # noqa: BLE001 -- mirrors the TypeScript original's catch-all init guard
        print_error(f"Unexpected error while initializing scoring sources: {err}", json_mode)
        return 2

    target = url or screenshot or ""

    try:
        result = score_composite(sources, ScoreInput(url=url, screenshot_path=screenshot))
        print_report(result, target, options.rubric, json_mode)

        if fail_below is not None and result.composite_score < fail_below:
            return 1
        return 0
    except MissingApiKeyError as err:
        print_error(str(err), json_mode)
        return 2
    except Exception as err:  # noqa: BLE001 -- mirrors the TypeScript original's catch-all scoring guard
        print_error(f'slop-eval failed to score "{target}": {err}', json_mode)
        return 2


def build_parser() -> argparse.ArgumentParser:
    """Builds the argparse parser. Exported so tests can inspect the `score` subcommand's flags/help text."""
    parser = argparse.ArgumentParser(
        prog="slop-eval",
        description=(
            'Scores AI-generated UI for genericness ("slop") using an LLM-judge rubric. '
            "This is a heuristic quality signal, not a certification -- see the score subcommand for details."
        ),
    )
    parser.add_argument("--version", action="version", version=f"slop-eval-cli {_VERSION}")

    subparsers = parser.add_subparsers(dest="command")

    score_parser = subparsers.add_parser(
        "score",
        help="Score a URL or screenshot for AI-UI genericness against a versioned rubric.",
        description=_SCORE_DESCRIPTION,
    )
    score_parser.add_argument(
        "--url", default=None, help="URL to score (fetched as raw HTML/text -- see limitation note above)"
    )
    score_parser.add_argument(
        "--screenshot", default=None, help="path to a screenshot image to score (preferred over --url)"
    )
    score_parser.add_argument(
        "--rubric", default="v1", help='rubric version to use, reads slop_eval/rubric/<name>.json (default: "v1")'
    )
    score_parser.add_argument(
        "--json", action="store_true", default=False, help="output structured JSON instead of a human-readable report"
    )
    score_parser.add_argument(
        "--fail-below",
        default=None,
        metavar="N",
        help="exit code 1 if the composite score is below this threshold (0-100); no threshold by default",
    )

    return parser


def is_json_mode_requested(argv: List[str]) -> bool:
    """Whether --json appears anywhere in argv, regardless of flag order -- mirrors the TypeScript original's helper of the same name."""
    return "--json" in argv


def run_cli(argv: List[str]) -> int:
    """`argv` follows the sys.argv convention: argv[0] is the program name, real arguments start at argv[1]."""
    parser = build_parser()
    args = parser.parse_args(argv[1:])

    if args.command != "score":
        parser.print_help()
        return 0

    options = ScoreOptions(
        url=args.url,
        screenshot=args.screenshot,
        rubric=args.rubric,
        json=args.json,
        fail_below=args.fail_below,
    )
    return run_score(options)


def main() -> None:
    sys.exit(run_cli(sys.argv))


if __name__ == "__main__":
    main()
