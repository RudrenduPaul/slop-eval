"""
Ported from test/llm-judge-source.test.ts. Every test in this file must
never make a real network call to the Anthropic API -- the client is
replaced with a fake before each test via monkeypatch, and any real URL
fetch is monkeypatched at the urllib level.
"""
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

import slop_eval.sources.llm_judge as llm_judge_module
from slop_eval.errors import MissingApiKeyError, RubricLoadError
from slop_eval.sources.base import ScoreInput
from slop_eval.sources.llm_judge import LLMJudgeSource, load_rubric

FIXTURE_PNG = str(Path(__file__).parent / "fixtures" / "sample.png")

ALL_CATEGORIES_MEDIUM = [
    {"categoryId": "layout-novelty", "score": 5, "evidence": "evidence a"},
    {"categoryId": "visual-identity-distinctiveness", "score": 5, "evidence": "evidence b"},
    {"categoryId": "component-pattern-novelty", "score": 5, "evidence": "evidence c"},
]


class FakeMessages:
    def __init__(self):
        self.calls = []
        self._response = None

    def set_response(self, content):
        self._response = SimpleNamespace(content=content)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class FakeAnthropic:
    """Stand-in for anthropic.Anthropic. One shared instance per test via a factory closure."""

    instances = []

    def __init__(self, api_key=None):
        self.api_key = api_key
        self.messages = FakeMessages()
        FakeAnthropic.instances.append(self)


def _tool_use_block(findings):
    return [SimpleNamespace(type="tool_use", id="toolu_1", name="submit_slop_scores", input={"findings": findings})]


@pytest.fixture(autouse=True)
def patch_anthropic(monkeypatch):
    FakeAnthropic.instances = []
    monkeypatch.setattr(llm_judge_module, "Anthropic", FakeAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    yield


@pytest.fixture(autouse=True)
def patch_dns_resolution(monkeypatch):
    """
    _assert_url_is_safe_to_fetch resolves the URL's hostname via
    socket.getaddrinfo before urlopen is ever reached. Stub it to a
    public-looking IP by default so the existing fake `.example` hostnames
    below keep working without a real DNS lookup -- individual SSRF tests
    override this per-test to simulate a private/internal resolution.
    """

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(llm_judge_module.socket, "getaddrinfo", fake_getaddrinfo)
    yield


class TestLoadRubric:
    def test_loads_the_v1_rubric_with_its_3_documented_categories(self):
        rubric = load_rubric("v1")
        assert len(rubric.categories) == 3
        assert [c.id for c in rubric.categories] == [
            "layout-novelty",
            "visual-identity-distinctiveness",
            "component-pattern-novelty",
        ]

    def test_raises_rubric_load_error_for_a_rubric_name_that_does_not_exist(self):
        with pytest.raises(RubricLoadError):
            load_rubric("does-not-exist")

    def test_raises_rubric_load_error_for_a_rubric_name_with_path_traversal_segments(self):
        with pytest.raises(RubricLoadError, match="is invalid"):
            load_rubric("../../../etc/passwd")

    def test_raises_rubric_load_error_for_malformed_json(self, tmp_path):
        rubric_dir = Path(llm_judge_module.__file__).parent.parent / "rubric"
        rubric_name = "test-malformed-rubric"
        rubric_path = rubric_dir / f"{rubric_name}.json"
        rubric_path.write_text("{ this is not valid json")
        try:
            with pytest.raises(RubricLoadError, match="not valid JSON"):
                load_rubric(rubric_name)
        finally:
            rubric_path.unlink()

    def test_raises_rubric_load_error_when_categories_is_missing_or_empty(self, tmp_path):
        rubric_dir = Path(llm_judge_module.__file__).parent.parent / "rubric"
        rubric_name = "test-empty-categories"
        rubric_path = rubric_dir / f"{rubric_name}.json"
        rubric_path.write_text('{"version": "v1", "description": "x", "categories": []}')
        try:
            with pytest.raises(RubricLoadError, match="categories"):
                load_rubric(rubric_name)
        finally:
            rubric_path.unlink()

    def test_raises_rubric_load_error_when_a_category_is_missing_a_required_field(self, tmp_path):
        rubric_dir = Path(llm_judge_module.__file__).parent.parent / "rubric"
        rubric_name = "test-missing-field"
        rubric_path = rubric_dir / f"{rubric_name}.json"
        rubric_path.write_text('{"version": "v1", "description": "x", "categories": [{"id": "a"}]}')
        try:
            with pytest.raises(RubricLoadError, match='missing "id", "name", or "description"'):
                load_rubric(rubric_name)
        finally:
            rubric_path.unlink()


def test_raises_missing_api_key_error_with_actionable_message_when_key_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    source = LLMJudgeSource("v1", str(tmp_path))

    with pytest.raises(MissingApiKeyError, match="ANTHROPIC_API_KEY"):
        source.score(ScoreInput(screenshot_path=FIXTURE_PNG))

    assert FakeAnthropic.instances == []


def test_scores_a_screenshot_and_maps_each_rubric_category_to_a_finding(tmp_path):
    source = LLMJudgeSource("v1", str(tmp_path))
    source._get_client()  # force client construction so we can pre-load its fake response
    FakeAnthropic.instances[0].messages.set_response(
        _tool_use_block(
            [
                {"categoryId": "layout-novelty", "score": 4, "evidence": "generic hero layout"},
                {"categoryId": "visual-identity-distinctiveness", "score": 8, "evidence": "unique palette"},
                {"categoryId": "component-pattern-novelty", "score": 7, "evidence": "custom cards"},
            ]
        )
    )

    findings = source.score(ScoreInput(screenshot_path=FIXTURE_PNG))

    assert len(findings) == 3
    layout = next(f for f in findings if f.rule_id == "llm-judge.layout-novelty")
    assert layout.score == 4
    assert layout.status == "flag"
    assert layout.evidence == "generic hero layout"

    visual = next(f for f in findings if f.rule_id == "llm-judge.visual-identity-distinctiveness")
    assert visual.score == 8
    assert visual.status == "pass"
    assert len(FakeAnthropic.instances[0].messages.calls) == 1


def test_caches_identical_screenshot_input_so_api_is_called_exactly_once(tmp_path):
    source = LLMJudgeSource("v1", str(tmp_path))
    source._get_client()
    FakeAnthropic.instances[0].messages.set_response(_tool_use_block(ALL_CATEGORIES_MEDIUM))

    source.score(ScoreInput(screenshot_path=FIXTURE_PNG))
    source.score(ScoreInput(screenshot_path=FIXTURE_PNG))

    assert len(FakeAnthropic.instances[0].messages.calls) == 1


def test_marks_a_rubric_category_not_scored_if_the_judge_response_omits_it(tmp_path):
    source = LLMJudgeSource("v1", str(tmp_path))
    source._get_client()
    FakeAnthropic.instances[0].messages.set_response(
        _tool_use_block([{"categoryId": "layout-novelty", "score": 5, "evidence": "x"}])
    )

    findings = source.score(ScoreInput(screenshot_path=FIXTURE_PNG))

    not_scored = [f for f in findings if f.status == "not_scored"]
    assert len(not_scored) == 2
    assert all(len(f.evidence) > 0 for f in not_scored)


def test_clamps_out_of_range_scores_into_0_10(tmp_path):
    source = LLMJudgeSource("v1", str(tmp_path))
    source._get_client()
    FakeAnthropic.instances[0].messages.set_response(
        _tool_use_block(
            [
                {"categoryId": "layout-novelty", "score": 15, "evidence": "x"},
                {"categoryId": "visual-identity-distinctiveness", "score": -3, "evidence": "x"},
                {"categoryId": "component-pattern-novelty", "score": 5, "evidence": "x"},
            ]
        )
    )

    findings = source.score(ScoreInput(screenshot_path=FIXTURE_PNG))

    assert next(f for f in findings if f.rule_id == "llm-judge.layout-novelty").score == 10
    assert next(f for f in findings if f.rule_id == "llm-judge.visual-identity-distinctiveness").score == 0


def test_raises_a_clear_error_when_the_judge_response_has_no_tool_use_block(tmp_path):
    source = LLMJudgeSource("v1", str(tmp_path))
    source._get_client()
    FakeAnthropic.instances[0].messages.set_response([SimpleNamespace(type="text", text="I refuse to use tools.")])

    with pytest.raises(RuntimeError, match="structured tool-use"):
        source.score(ScoreInput(screenshot_path=FIXTURE_PNG))


def test_scores_a_url_by_fetching_its_text_content(monkeypatch, tmp_path):
    class FakeResponse:
        def __init__(self):
            self.headers = {}

        def read(self):
            return b"<html><body><h1>Hi</h1></body></html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(llm_judge_module.urllib.request, "urlopen", fake_urlopen)

    source = LLMJudgeSource("v1", str(tmp_path))
    source._get_client()
    FakeAnthropic.instances[0].messages.set_response(_tool_use_block(ALL_CATEGORIES_MEDIUM))

    findings = source.score(ScoreInput(url="https://example.com"))

    assert len(findings) == 3
    assert captured["url"] == "https://example.com"


def test_raises_a_clear_error_when_the_url_fetch_returns_a_non_ok_response(monkeypatch, tmp_path):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", None, None)

    monkeypatch.setattr(llm_judge_module.urllib.request, "urlopen", fake_urlopen)
    source = LLMJudgeSource("v1", str(tmp_path))

    with pytest.raises(RuntimeError, match="404"):
        source.score(ScoreInput(url="https://example.com/missing"))


def test_raises_a_clear_error_when_the_url_fetch_itself_fails(monkeypatch, tmp_path):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("DNS lookup failed")

    monkeypatch.setattr(llm_judge_module.urllib.request, "urlopen", fake_urlopen)
    source = LLMJudgeSource("v1", str(tmp_path))

    with pytest.raises(RuntimeError, match="Could not fetch URL"):
        source.score(ScoreInput(url="https://unreachable.example"))


def test_reports_a_clear_timeout_error_when_the_url_fetch_times_out(monkeypatch, tmp_path):
    def fake_urlopen(req, timeout=None):
        raise socket.timeout("timed out")

    monkeypatch.setattr(llm_judge_module.urllib.request, "urlopen", fake_urlopen)
    source = LLMJudgeSource("v1", str(tmp_path))

    with pytest.raises(RuntimeError, match="timed out after"):
        source.score(ScoreInput(url="https://slow.example"))


def test_rejects_a_url_response_whose_content_length_exceeds_the_size_cap(monkeypatch, tmp_path):
    class FakeResponse:
        def __init__(self):
            self.headers = {"Content-Length": str(50 * 1024 * 1024)}

        def read(self):
            raise AssertionError("body should not be read once the Content-Length cap is exceeded")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        return FakeResponse()

    monkeypatch.setattr(llm_judge_module.urllib.request, "urlopen", fake_urlopen)
    source = LLMJudgeSource("v1", str(tmp_path))

    with pytest.raises(RuntimeError, match="exceeds the"):
        source.score(ScoreInput(url="https://huge.example"))


def test_rejects_a_file_url_without_ever_calling_urlopen(monkeypatch, tmp_path):
    def fake_urlopen(req, timeout=None):
        raise AssertionError("urlopen should never be reached for a blocked scheme")

    monkeypatch.setattr(llm_judge_module.urllib.request, "urlopen", fake_urlopen)
    source = LLMJudgeSource("v1", str(tmp_path))

    with pytest.raises(RuntimeError, match="only http/https URLs"):
        source.score(ScoreInput(url="file:///etc/passwd"))


def test_rejects_a_url_that_resolves_to_a_loopback_address(monkeypatch, tmp_path):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    def fake_urlopen(req, timeout=None):
        raise AssertionError("urlopen should never be reached once the SSRF guard rejects the host")

    monkeypatch.setattr(llm_judge_module.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(llm_judge_module.urllib.request, "urlopen", fake_urlopen)
    source = LLMJudgeSource("v1", str(tmp_path))

    with pytest.raises(RuntimeError, match="private/internal address"):
        source.score(ScoreInput(url="https://internal.example"))


def test_rejects_a_url_that_resolves_to_the_cloud_metadata_address(monkeypatch, tmp_path):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    def fake_urlopen(req, timeout=None):
        raise AssertionError("urlopen should never be reached once the SSRF guard rejects the host")

    monkeypatch.setattr(llm_judge_module.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(llm_judge_module.urllib.request, "urlopen", fake_urlopen)
    source = LLMJudgeSource("v1", str(tmp_path))

    with pytest.raises(RuntimeError, match="private/internal address"):
        source.score(ScoreInput(url="https://metadata.example"))


def test_raises_when_neither_url_nor_screenshot_path_is_provided(tmp_path):
    source = LLMJudgeSource("v1", str(tmp_path))
    with pytest.raises(RuntimeError, match="requires either"):
        source.score(ScoreInput())


def test_raises_a_clear_error_for_an_unreadable_screenshot_path(tmp_path):
    source = LLMJudgeSource("v1", str(tmp_path))
    with pytest.raises(RuntimeError, match="Could not read screenshot"):
        source.score(ScoreInput(screenshot_path="/nonexistent/path/nope.png"))


def test_respects_an_explicit_model_override_over_env_var_and_default(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_MODEL", "should-be-overridden")
    source = LLMJudgeSource("v1", str(tmp_path), model="claude-haiku-4-5")
    source._get_client()
    FakeAnthropic.instances[0].messages.set_response(_tool_use_block(ALL_CATEGORIES_MEDIUM))

    source.score(ScoreInput(screenshot_path=FIXTURE_PNG))

    assert FakeAnthropic.instances[0].messages.calls[0]["model"] == "claude-haiku-4-5"


def test_reuses_the_same_client_instance_across_two_cache_miss_inputs(tmp_path):
    source = LLMJudgeSource("v1", str(tmp_path))
    source._get_client()
    FakeAnthropic.instances[0].messages.set_response(_tool_use_block(ALL_CATEGORIES_MEDIUM))

    # Different byte content than FIXTURE_PNG -> different content hash ->
    # guaranteed second cache miss, so _call_judge (and therefore
    # _get_client) runs a second time on the *same* source instance.
    second_screenshot = tmp_path / "second.png"
    second_screenshot.write_bytes(Path(FIXTURE_PNG).read_bytes() + b"\x00")

    source.score(ScoreInput(screenshot_path=FIXTURE_PNG))
    source.score(ScoreInput(screenshot_path=str(second_screenshot)))

    assert len(FakeAnthropic.instances[0].messages.calls) == 2
    assert len(FakeAnthropic.instances) == 1
