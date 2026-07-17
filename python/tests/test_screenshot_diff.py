"""Ported from test/screenshot-diff-source.test.ts."""
from slop_eval.sources.base import ScoreInput
from slop_eval.sources.screenshot_diff import ScreenshotDiffSource


def test_always_returns_exactly_one_not_scored_finding_regardless_of_input():
    source = ScreenshotDiffSource()

    from_screenshot = source.score(ScoreInput(screenshot_path="whatever.png"))
    from_url = source.score(ScoreInput(url="https://example.com"))
    from_empty = source.score(ScoreInput())

    for findings in (from_screenshot, from_url, from_empty):
        assert len(findings) == 1
        assert findings[0].status == "not_scored"
        assert findings[0].category == "screenshot-diff-vs-corpus"
        assert "corpus" in findings[0].evidence.lower()


def test_exposes_a_stable_source_name():
    source = ScreenshotDiffSource()
    assert source.name == "screenshot-diff-vs-corpus"
