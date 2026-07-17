"""Ported from test/composite.test.ts."""
from slop_eval.scorer import score_composite
from slop_eval.sources.base import RuleFinding, ScoreInput


class FakeSource:
    def __init__(self, name, findings):
        self.name = name
        self._findings = findings

    def score(self, score_input):
        return self._findings


def test_averages_non_not_scored_findings_and_scales_0_10_to_0_100():
    source = FakeSource(
        "fake",
        [
            RuleFinding(rule_id="a", category="A", score=8, evidence="e", status="pass"),
            RuleFinding(rule_id="b", category="B", score=4, evidence="e", status="flag"),
        ],
    )

    result = score_composite([source], ScoreInput())

    assert result.composite_score == 60
    assert len(result.findings) == 2


def test_excludes_not_scored_findings_from_average_but_keeps_them_in_list():
    source = FakeSource(
        "fake",
        [
            RuleFinding(rule_id="a", category="A", score=10, evidence="e", status="pass"),
            RuleFinding(rule_id="b", category="B", score=0, evidence="no corpus", status="not_scored"),
        ],
    )

    result = score_composite([source], ScoreInput())

    assert result.composite_score == 100
    assert len(result.findings) == 2
    assert any(f.status == "not_scored" for f in result.findings)


def test_returns_0_when_every_finding_is_not_scored():
    source = FakeSource(
        "fake", [RuleFinding(rule_id="a", category="A", score=0, evidence="no corpus", status="not_scored")]
    )

    result = score_composite([source], ScoreInput())

    assert result.composite_score == 0


def test_returns_0_and_empty_findings_when_no_sources_at_all():
    result = score_composite([], ScoreInput())

    assert result.composite_score == 0
    assert result.findings == []


def test_runs_sources_in_order_and_flattens_findings():
    s1 = FakeSource("s1", [RuleFinding(rule_id="a", category="A", score=10, evidence="e", status="pass")])
    s2 = FakeSource("s2", [RuleFinding(rule_id="b", category="B", score=0, evidence="e", status="flag")])

    result = score_composite([s1, s2], ScoreInput())

    assert [f.rule_id for f in result.findings] == ["a", "b"]
    assert result.composite_score == 50


def test_rounds_to_a_clean_fraction_for_uneven_averages():
    source = FakeSource(
        "fake",
        [
            RuleFinding(rule_id="a", category="A", score=7, evidence="e", status="pass"),
            RuleFinding(rule_id="b", category="B", score=5, evidence="e", status="flag"),
            RuleFinding(rule_id="c", category="C", score=4, evidence="e", status="flag"),
        ],
    )

    result = score_composite([source], ScoreInput())

    # (7 + 5 + 4) / 3 = 5.333... * 10 = 53.33...
    assert round(result.composite_score, 1) == 53.3
