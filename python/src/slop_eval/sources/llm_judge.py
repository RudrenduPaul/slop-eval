"""
LLMJudgeSource -- slop-eval's first-party RuleSource implementation.
Ported from src/sources/LLMJudgeSource.ts, using the official `anthropic`
Python SDK rather than reimplementing raw HTTP calls.

Scores a URL or screenshot against the rubric in slop_eval/rubric/<name>.json
by calling the Anthropic API with a forced tool call, so the response is
reliably parseable JSON rather than free text that has to be regexed apart.

v0.1 input handling (identical to the TypeScript original):
  - `screenshot_path` is the well-supported path: the image is read and
    sent to the judge as base64, giving it a real rendered view of the UI.
  - `url` is a documented v0.1 fallback: this tool does not bundle a
    headless browser to render the page into a screenshot -- that's out of
    scope for v0.1 by design. Instead the raw HTML/text response body is
    fetched (via the stdlib's urllib, not the `anthropic` SDK) and given to
    the judge as text. The judge can reason about markup, inline styles,
    and copy, but not the actual rendered visual layout -- so --screenshot
    is the stronger signal. This limitation is also stated in the CLI's
    --help text.

Every real judge call is wrapped through the content-hash cache in
slop_eval/cache.py, so identical input never triggers a second API call.

Along with scorer.py, this module directly produces the CI-gate verdict --
tests must never call the real Anthropic API; every test mocks the client.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.resources
import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from anthropic import Anthropic

from ..errors import MissingApiKeyError, RubricLoadError
from .base import RuleFinding, ScoreInput

# Default model per this repo's rubric task: a rubric-scoring judge is a
# bounded classification/extraction call against a fixed rubric, not
# open-ended reasoning, so a mid-tier model is the right cost/quality
# default for a BYO-key tool invoked repeatedly in CI. Override with
# ANTHROPIC_MODEL. Kept identical to the TypeScript original's default.
DEFAULT_MODEL = "claude-sonnet-5"

# Hard cap on how long --url mode will wait for the page fetch. Without
# this, a target URL that never completes the response (a hung dev-preview
# deploy, a slow proxy, a streaming endpoint that never closes) hangs the
# whole CI job until the runner's own top-level timeout kills it, instead of
# failing fast with an actionable error. Override with
# SLOP_EVAL_FETCH_TIMEOUT_MS. Ported from URL_FETCH_TIMEOUT_MS.
URL_FETCH_TIMEOUT_MS = int(os.environ.get("SLOP_EVAL_FETCH_TIMEOUT_MS") or 30_000)

# Best-effort cap on response body size for --url mode, checked against the
# Content-Length header when the server reports one, before the body is
# read. Does not stop a server that lies about or omits Content-Length
# while streaming an unbounded body, but does stop the common case of an
# honestly-huge page from being read fully into memory. Ported from
# URL_MAX_CONTENT_LENGTH_BYTES.
URL_MAX_CONTENT_LENGTH_BYTES = 10 * 1024 * 1024

_MEDIA_TYPE_BY_EXT = {
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "gif": "gif",
    "webp": "webp",
}


@dataclass
class RubricCategory:
    id: str
    name: str
    description: str


@dataclass
class Rubric:
    version: str
    description: str
    categories: List[RubricCategory]


# rubric_name is joined straight into a package-resource path below --
# restricting it to a bare name (no separators or ".." segments) before that
# join closes off path traversal for any caller that ever wires --rubric to
# something other than a maintainer-chosen local flag.
_RUBRIC_NAME_PATTERN = re.compile(r"^[\w-]+$")


def load_rubric(rubric_name: str) -> Rubric:
    """
    Loads slop_eval/rubric/<rubric_name>.json, bundled inside the installed
    package (via importlib.resources, not a repo-relative filesystem path,
    since a pip-installed wheel has no source checkout to resolve against).
    """
    if not _RUBRIC_NAME_PATTERN.match(rubric_name):
        raise RubricLoadError(
            f'Rubric name "{rubric_name}" is invalid -- expected letters, digits, "-", or "_" only.'
        )

    resource = importlib.resources.files("slop_eval").joinpath("rubric", f"{rubric_name}.json")

    if not resource.is_file():
        raise RubricLoadError(
            f'Rubric "{rubric_name}" not found (looked for {resource}). '
            "Available rubrics ship inside the slop_eval package's rubric/ directory -- "
            "pass --rubric with one of those names (without the .json extension)."
        )

    try:
        raw = resource.read_text(encoding="utf-8")
    except OSError as err:
        raise RubricLoadError(f"Could not read rubric file at {resource}: {err}") from err

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as err:
        raise RubricLoadError(f"Rubric file at {resource} is not valid JSON: {err}") from err

    if not isinstance(parsed, dict) or not isinstance(parsed.get("categories"), list) or not parsed["categories"]:
        raise RubricLoadError(
            f'Rubric file at {resource} is malformed: expected a "categories" array with at least one entry.'
        )

    categories: List[RubricCategory] = []
    for cat in parsed["categories"]:
        if not cat.get("id") or not cat.get("name") or not cat.get("description"):
            raise RubricLoadError(
                f'Rubric file at {resource} has a category missing "id", "name", or "description": {json.dumps(cat)}'
            )
        categories.append(RubricCategory(id=cat["id"], name=cat["name"], description=cat["description"]))

    return Rubric(version=parsed.get("version", rubric_name), description=parsed.get("description", ""), categories=categories)


class LLMJudgeSource:
    name = "llm-judge"

    def __init__(self, rubric_name: str = "v1", cache_dir: Optional[str] = None, model: Optional[str] = None) -> None:
        """
        :param rubric_name: which rubric/<name>.json to load and score against.
        :param cache_dir: override the judge-cache directory (mainly for tests).
        :param model: override the Anthropic model id (defaults to ANTHROPIC_MODEL env var, then DEFAULT_MODEL).
        """
        self.rubric = load_rubric(rubric_name)
        self.cache_dir = cache_dir
        self.model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self._client: Optional[Anthropic] = None

    def _get_client(self) -> Anthropic:
        if self._client is not None:
            return self._client
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise MissingApiKeyError()
        self._client = Anthropic(api_key=api_key)
        return self._client

    def score(self, score_input: ScoreInput) -> List[RuleFinding]:
        from ..cache import get_cached_or_compute, DEFAULT_CACHE_DIR

        judge_input, content_hash = self._load_input(score_input)
        cache_dir = self.cache_dir if self.cache_dir is not None else DEFAULT_CACHE_DIR
        cached = get_cached_or_compute(content_hash, lambda: self._call_judge(judge_input), cache_dir)
        return [RuleFinding(**entry) for entry in cached]

    def _load_input(self, score_input: ScoreInput) -> Any:
        if score_input.screenshot_path:
            path = Path(score_input.screenshot_path)
            try:
                data = path.read_bytes()
            except OSError as err:
                raise RuntimeError(f"Could not read screenshot at {score_input.screenshot_path}: {err}") from err

            content_hash = hashlib.sha256(data).hexdigest()
            ext = path.suffix.lower().lstrip(".")
            media_type = _MEDIA_TYPE_BY_EXT.get(ext, "png")
            judge_input = {"kind": "image", "base64": base64.b64encode(data).decode("ascii"), "media_type": media_type}
            return judge_input, content_hash

        if score_input.url:
            text = self._fetch_url(score_input.url)
            content_hash = hashlib.sha256(f"{score_input.url}\n{text}".encode("utf-8")).hexdigest()
            judge_input = {"kind": "text", "url": score_input.url, "text": text}
            return judge_input, content_hash

        raise RuntimeError('ScoreInput requires either "url" or "screenshot_path" to be set.')

    @staticmethod
    def _assert_url_is_safe_to_fetch(url: str) -> None:
        """
        Blocks SSRF/local-file-read into internal targets before --url mode
        fetches anything. Without a scheme check, urllib's built-in file://
        handler turns --url into an arbitrary local-file-read primitive
        (contents get embedded in the judge prompt and can resurface in the
        JSON output); without an IP check, any RFC1918/loopback/link-local
        target -- including 169.254.169.254, the AWS/GCP/Azure
        instance-metadata endpoint, which falls under the link-local block --
        is reachable if --url is ever wired to input an attacker can
        influence (this tool is meant to be embedded in other people's CI via
        the bundled GitHub Action).

        This validates the resolved IP at lookup time, not at connection
        time, so it does not fully close a DNS-rebinding attack (a name that
        resolves to a public IP during this check but a private one when
        urlopen actually connects) -- fully closing that requires a custom
        socket factory that re-validates the IP it connects to, out of scope
        for this fix.
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise RuntimeError(
                f"Could not fetch URL {url}: only http/https URLs are supported for --url mode "
                f'(got "{parsed.scheme}").'
            )
        hostname = parsed.hostname
        if not hostname or hostname.lower() == "metadata.google.internal":
            raise RuntimeError(f'Could not fetch URL {url}: host "{hostname}" is not allowed for --url mode.')
        try:
            resolved = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
        except socket.gaierror as err:
            raise RuntimeError(f'Could not fetch URL {url}: could not resolve host "{hostname}": {err}') from err
        for ip_str in resolved:
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise RuntimeError(
                    f'Could not fetch URL {url}: host "{hostname}" resolves to a private/internal address '
                    f"({ip_str}), which is not allowed for --url mode."
                )

    def _fetch_url(self, url: str) -> str:
        self._assert_url_is_safe_to_fetch(url)
        req = urllib.request.Request(url, headers={"User-Agent": "slop-eval-cli"})
        try:
            with urllib.request.urlopen(req, timeout=URL_FETCH_TIMEOUT_MS / 1000) as res:
                content_length_header = res.headers.get("Content-Length")
                if content_length_header is not None:
                    try:
                        content_length = int(content_length_header)
                    except ValueError:
                        content_length = None
                    if content_length is not None and content_length > URL_MAX_CONTENT_LENGTH_BYTES:
                        raise RuntimeError(
                            f"Could not fetch URL {url}: response body ({content_length} bytes) exceeds the "
                            f"{URL_MAX_CONTENT_LENGTH_BYTES}-byte cap for --url mode -- render the page yourself "
                            "and pass --screenshot instead."
                        )
                body = res.read()
                return body.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as err:
            raise RuntimeError(f"Could not fetch URL {url}: HTTP {err.code} {err.reason}") from err
        except TimeoutError as err:
            raise RuntimeError(f"Could not fetch URL {url}: timed out after {URL_FETCH_TIMEOUT_MS}ms") from err
        except urllib.error.URLError as err:
            reason = err.reason
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise RuntimeError(f"Could not fetch URL {url}: timed out after {URL_FETCH_TIMEOUT_MS}ms") from err
            raise RuntimeError(f"Could not fetch URL {url}: {reason}") from err

    def _call_judge(self, judge_input: Dict[str, Any]) -> List[Dict[str, Any]]:
        client = self._get_client()
        categories = self.rubric.categories

        rubric_text = "\n".join(f'- id: "{c.id}" ({c.name}) -- {c.description}' for c in categories)

        if judge_input["kind"] == "image":
            instructions = (
                'You are scoring a screenshot of an AI-generated web UI for genericness ("slop") against the rubric below. '
                "For each rubric category, give a 0-10 score (0 = maximally generic/derivative, 10 = maximally distinctive/original) "
                "and a specific, cited evidence string describing exactly what you observed -- never a generic statement like "
                '"could be more original." Call the submit_slop_scores tool with one entry per category.'
            )
            prompt_text = f"{instructions}\n\nRubric categories:\n{rubric_text}"
        else:
            instructions = (
                'You are scoring the raw HTML/text content of a web page for genericness ("slop") against the rubric below. '
                "Note: no rendered screenshot was available (v0.1 limitation -- URL mode has no headless-browser renderer), so "
                "judge from markup structure, inline styles, class names, and copy rather than final visual layout. "
                "For each rubric category, give a 0-10 score (0 = maximally generic/derivative, 10 = maximally distinctive/original) "
                "and a specific, cited evidence string describing exactly what you observed -- never a generic statement. "
                "Call the submit_slop_scores tool with one entry per category."
            )
            prompt_text = (
                f"{instructions}\n\nRubric categories:\n{rubric_text}\n\nPage URL: {judge_input['url']}\n\n"
                f"Page content (truncated to 20000 characters):\n{judge_input['text'][:20000]}"
            )

        if judge_input["kind"] == "image":
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": f"image/{judge_input['media_type']}",
                        "data": judge_input["base64"],
                    },
                },
                {"type": "text", "text": prompt_text},
            ]
        else:
            content = [{"type": "text", "text": prompt_text}]

        tool_schema = {
            "name": "submit_slop_scores",
            "description": "Submit a 0-10 score and specific evidence for every rubric category.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "categoryId": {
                                    "type": "string",
                                    "enum": [c.id for c in categories],
                                    "description": "Must exactly match one of the rubric category ids.",
                                },
                                "score": {"type": "number", "description": "0-10 score for this category."},
                                "evidence": {
                                    "type": "string",
                                    "description": "Specific, cited reason for the score -- never a generic statement.",
                                },
                            },
                            "required": ["categoryId", "score", "evidence"],
                        },
                    }
                },
                "required": ["findings"],
            },
        }

        response = client.messages.create(
            model=self.model,
            max_tokens=2048,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": "submit_slop_scores"},
            messages=[{"role": "user", "content": content}],
        )

        tool_use_block = next((block for block in response.content if getattr(block, "type", None) == "tool_use"), None)

        if tool_use_block is None:
            raise RuntimeError(
                "LLM judge did not return the expected structured tool-use response. This is an unexpected "
                "API response shape, not a scoring result."
            )

        parsed_findings = tool_use_block.input.get("findings", [])

        results: List[Dict[str, Any]] = []
        for cat in categories:
            found = next((f for f in parsed_findings if f.get("categoryId") == cat.id), None)
            if found is None:
                results.append(
                    {
                        "rule_id": f"llm-judge.{cat.id}",
                        "category": cat.name,
                        "score": 0,
                        "evidence": (
                            f'The LLM judge did not return a finding for rubric category "{cat.name}" -- '
                            "treating as unscored rather than fabricating a value."
                        ),
                        "status": "not_scored",
                    }
                )
                continue
            clamped_score = max(0, min(10, found["score"]))
            results.append(
                {
                    "rule_id": f"llm-judge.{cat.id}",
                    "category": cat.name,
                    "score": clamped_score,
                    "evidence": found["evidence"],
                    "status": "pass" if clamped_score >= 6 else "flag",
                }
            )
        return results
