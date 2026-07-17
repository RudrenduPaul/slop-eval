"""Ported from test/cli.test.ts."""
import json
from pathlib import Path

import pytest

from slop_eval.cli import ScoreOptions, build_parser, is_json_mode_requested, run_cli, run_score
from slop_eval.sources.base import RuleFinding
from slop_eval.sources.llm_judge import LLMJudgeSource

FIXTURE_PNG = str(Path(__file__).parent / "fixtures" / "sample.png")


def fake_sources(findings):
    class FakeSource:
        name = "fake"

        def score(self, score_input):
            return findings

    return lambda rubric: [FakeSource()]


class TestRunScore:
    def test_exits_2_when_neither_url_nor_screenshot_is_given(self, capsys):
        code = run_score(ScoreOptions(url=None, screenshot=None, rubric="v1", json=False))
        assert code == 2
        assert "Error:" in capsys.readouterr().err

    def test_exits_2_when_both_url_and_screenshot_are_given(self):
        code = run_score(ScoreOptions(url="https://x.example", screenshot="a.png", rubric="v1", json=False))
        assert code == 2

    def test_emits_valid_json_for_the_usage_error_when_json_is_passed(self, capsys):
        code = run_score(ScoreOptions(url=None, screenshot=None, rubric="v1", json=True))
        assert code == 2
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "error" in parsed
        assert captured.err == ""

    def test_exits_0_with_no_fail_below_threshold_regardless_of_score(self):
        code = run_score(
            ScoreOptions(url="https://example.com", rubric="v1", json=True),
            fake_sources([RuleFinding(rule_id="a", category="A", score=1, evidence="e", status="flag")]),
        )
        assert code == 0

    def test_exits_1_when_composite_score_is_below_fail_below(self):
        code = run_score(
            ScoreOptions(url="https://example.com", rubric="v1", json=True, fail_below="90"),
            fake_sources([RuleFinding(rule_id="a", category="A", score=1, evidence="e", status="flag")]),
        )
        assert code == 1

    def test_exits_0_when_composite_score_meets_fail_below(self):
        code = run_score(
            ScoreOptions(url="https://example.com", rubric="v1", json=True, fail_below="50"),
            fake_sources([RuleFinding(rule_id="a", category="A", score=9, evidence="e", status="pass")]),
        )
        assert code == 0

    def test_emits_the_documented_json_schema_on_a_successful_run(self, capsys):
        run_score(
            ScoreOptions(url="https://example.com", rubric="v1", json=True),
            fake_sources([RuleFinding(rule_id="a", category="A", score=9, evidence="e", status="pass")]),
        )
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["target"] == "https://example.com"
        assert parsed["rubric"] == "v1"
        assert "compositeScore" in parsed
        assert "findings" in parsed
        assert "summary" in parsed
        assert "disclaimer" in parsed

    def test_prints_a_human_readable_report_when_json_is_not_passed(self, capsys):
        run_score(
            ScoreOptions(screenshot=FIXTURE_PNG, rubric="v1", json=False),
            fake_sources(
                [RuleFinding(rule_id="a", category="A", score=9, evidence="specific evidence text", status="pass")]
            ),
        )
        output = capsys.readouterr().out
        with pytest.raises(json.JSONDecodeError):
            json.loads(output)
        assert "slop-eval v0.1" in output
        assert "specific evidence text" in output

    def test_exits_2_with_clear_json_error_when_api_key_missing(self, monkeypatch, capsys):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        code = run_score(
            ScoreOptions(screenshot=FIXTURE_PNG, rubric="v1", json=True),
            lambda rubric: [LLMJudgeSource(rubric)],
        )

        assert code == 2
        parsed = json.loads(capsys.readouterr().out)
        assert "error" in parsed
        assert "ANTHROPIC_API_KEY" in parsed["error"]

    def test_exits_2_with_clear_message_when_requested_rubric_does_not_exist(self, capsys):
        code = run_score(
            ScoreOptions(url="https://example.com", rubric="does-not-exist", json=False),
            lambda rubric: [LLMJudgeSource(rubric)],
        )
        assert code == 2
        assert "ubric" in capsys.readouterr().err

    def test_exits_2_with_clear_error_for_unreadable_screenshot_path_real_source(self, capsys):
        code = run_score(
            ScoreOptions(screenshot="/nonexistent/path/nope.png", rubric="v1", json=False),
            lambda rubric: [LLMJudgeSource(rubric)],
        )
        assert code == 2
        assert "Could not read screenshot" in capsys.readouterr().err

    def test_uses_the_default_real_source_builder_when_no_override_is_passed(self, capsys):
        code = run_score(ScoreOptions(screenshot="/nonexistent/path/nope.png", rubric="v1", json=False))
        assert code == 2
        assert "Could not read screenshot" in capsys.readouterr().err

    def test_exits_2_with_clear_message_when_build_sources_raises_a_non_rubric_error(self, capsys):
        def boom(rubric):
            raise Exception("boom -- unexpected init failure")

        code = run_score(ScoreOptions(url="https://example.com", rubric="v1", json=False), boom)
        assert code == 2
        assert "Unexpected error while initializing" in capsys.readouterr().err

    def test_exits_2_with_clear_json_error_for_a_non_numeric_fail_below(self, capsys):
        code = run_score(
            ScoreOptions(url="https://example.com", rubric="v1", json=True, fail_below="notanumber"),
            fake_sources([RuleFinding(rule_id="a", category="A", score=9, evidence="e", status="pass")]),
        )
        assert code == 2
        parsed = json.loads(capsys.readouterr().out)
        assert parsed == {"error": '--fail-below must be a number, got "notanumber"'}


class TestBuildParser:
    def test_exposes_a_score_subcommand_with_the_documented_flags(self):
        parser = build_parser()
        score_actions = {
            action.dest: action
            for action in parser._subparsers._group_actions[0].choices["score"]._actions
        }
        for flag in ("url", "screenshot", "rubric", "json", "fail_below"):
            assert flag in score_actions

    def test_documents_the_url_v0_1_fallback_limitation_in_the_score_description(self):
        parser = build_parser()
        score_parser = parser._subparsers._group_actions[0].choices["score"]
        assert "headless" in score_parser.description.lower()

    def test_is_json_mode_requested_detects_json_anywhere_in_argv(self):
        assert is_json_mode_requested(["slop-eval", "score", "--json", "--fail-below", "x"]) is True
        assert is_json_mode_requested(["slop-eval", "score", "--fail-below", "x", "--json"]) is True
        assert is_json_mode_requested(["slop-eval", "score", "--fail-below", "x"]) is False

    def test_run_cli_end_to_end_via_argv_returns_the_documented_exit_code(self, capsys):
        code = run_cli(["slop-eval", "score", "--screenshot", "/nonexistent/path/nope.png"])
        assert code == 2
        assert "Could not read screenshot" in capsys.readouterr().err

    def test_run_cli_with_no_subcommand_prints_help_and_returns_0(self, capsys):
        code = run_cli(["slop-eval"])
        assert code == 0
        assert "slop-eval" in capsys.readouterr().out
