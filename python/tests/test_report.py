"""Ported from test/report-writer.test.ts."""
from slop_eval.report import build_json_report, render_human_report
from slop_eval.scorer import CompositeResult
from slop_eval.sources.base import RuleFinding

SAMPLE_RESULT = CompositeResult(
    composite_score=61.6,
    findings=[
        RuleFinding(
            rule_id="llm-judge.layout-novelty",
            category="Layout novelty",
            score=4,
            evidence="Matches a hero+3-card+footer pattern common in template output.",
            status="flag",
        ),
        RuleFinding(
            rule_id="llm-judge.component-pattern-novelty",
            category="Component-pattern novelty",
            score=7,
            evidence="Cards use a custom asymmetric hover reveal, not a stock pattern.",
            status="pass",
        ),
        RuleFinding(
            rule_id="screenshot-diff.no-corpus-v0.1",
            category="screenshot-diff-vs-corpus",
            score=0,
            evidence="No corpus exists yet in v0.1.",
            status="not_scored",
        ),
    ],
)


def test_build_json_report_produces_documented_schema_with_rounded_score_and_summary():
    report = build_json_report(SAMPLE_RESULT, "https://example.com", "v1")

    assert report["target"] == "https://example.com"
    assert report["rubric"] == "v1"
    assert report["compositeScore"] == 62
    assert report["summary"] == {"pass": 1, "flagged": 1, "notScored": 1}
    assert len(report["findings"]) == 3
    assert "heuristic" in report["disclaimer"].lower()
    assert "not a certification" in report["disclaimer"].lower()


def test_render_human_report_includes_score_breakdown_and_disclaimer():
    text = render_human_report(SAMPLE_RESULT, "https://example.com", "v1")

    assert "Target: https://example.com" in text
    assert "Score: 62/100" in text
    assert "[FLAG]" in text
    assert "Layout novelty: 4/10" in text
    assert "[PASS]" in text
    assert "Component-pattern novelty: 7/10" in text
    assert "[NOT SCORED] screenshot-diff-vs-corpus" in text
    assert "Summary: 1 pass, 1 flagged, 1 not scored" in text
    assert "heuristic quality signal" in text.lower()


def test_render_human_report_never_omits_evidence_for_a_finding():
    text = render_human_report(SAMPLE_RESULT, "https://example.com", "v1")
    for finding in SAMPLE_RESULT.findings:
        assert finding.evidence in text
