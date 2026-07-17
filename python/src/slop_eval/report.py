"""
Report writer -- turns a composite scoring result into either a
human-readable terminal report or a structured JSON object, depending on
the caller's --json flag. Ported from src/report/writer.ts.

Every human-readable report states plainly that the score is a heuristic
quality signal, not a certification -- never implying "not AI-generated" or
"definitely slop," carried over from the TypeScript original's own rule.

The JSON schema this module produces (`target`, `rubric`, `compositeScore`,
`findings[]` with camelCase keys, `summary`, `disclaimer`) is kept
byte-for-byte identical in key casing to the npm CLI's `--json` output --
internal Python objects use snake_case (see sources/base.py's RuleFinding),
but the serialized wire format matches the TypeScript original exactly, so
a CI script or agent parsing --json output gets the same shape regardless
of which CLI produced it.
"""
from __future__ import annotations

import json
import sys
from typing import Dict, List

from .scorer import CompositeResult
from .sources.base import RuleFinding

DISCLAIMER = (
    "This score is a heuristic quality signal from an LLM judge, not a certification. "
    'It does not mean the UI "is" or "is not" AI-generated, and it is not a guarantee of '
    "quality in either direction."
)


def _summarize(findings: List[RuleFinding]) -> Dict[str, int]:
    return {
        "pass": sum(1 for f in findings if f.status == "pass"),
        "flagged": sum(1 for f in findings if f.status == "flag"),
        "notScored": sum(1 for f in findings if f.status == "not_scored"),
    }


def build_json_report(result: CompositeResult, target: str, rubric_name: str) -> Dict:
    """Builds the structured JSON report dict (used both by --json mode and by any programmatic caller)."""
    return {
        "target": target,
        "rubric": rubric_name,
        "compositeScore": round(result.composite_score),
        "findings": [
            {
                "ruleId": f.rule_id,
                "category": f.category,
                "score": f.score,
                "evidence": f.evidence,
                "status": f.status,
            }
            for f in result.findings
        ],
        "summary": _summarize(result.findings),
        "disclaimer": DISCLAIMER,
    }


def render_human_report(result: CompositeResult, target: str, rubric_name: str) -> str:
    """Renders the same data as a human-readable terminal report."""
    summary = _summarize(result.findings)
    lines: List[str] = []

    lines.append(f"slop-eval v0.1 -- AI-Slop Quality Score (rubric: {rubric_name})")
    lines.append(f"Target: {target}")
    lines.append("")
    lines.append(f"Score: {round(result.composite_score)}/100")
    lines.append("")

    for finding in result.findings:
        if finding.status == "not_scored":
            lines.append(f"[NOT SCORED] {finding.category}")
            lines.append(f"  {finding.evidence}")
        else:
            tag = "[PASS] " if finding.status == "pass" else "[FLAG] "
            lines.append(f"{tag} {finding.category}: {finding.score}/10")
            lines.append(f"  {finding.evidence}")
        lines.append("")

    lines.append(f"Summary: {summary['pass']} pass, {summary['flagged']} flagged, {summary['notScored']} not scored")
    lines.append("")
    lines.append(DISCLAIMER)

    return "\n".join(lines)


def print_report(result: CompositeResult, target: str, rubric_name: str, json_mode: bool) -> None:
    """Prints the report to stdout in the requested mode. Does not mix JSON and human-readable text."""
    if json_mode:
        print(json.dumps(build_json_report(result, target, rubric_name), indent=2))
    else:
        print(render_human_report(result, target, rubric_name))


def print_error(message: str, json_mode: bool) -> None:
    """
    Prints an error consistently across both output modes. JSON mode always
    emits valid JSON (an object with an "error" key) so a programmatic
    caller never has to branch on success vs. failure shape to find the
    error string.
    """
    if json_mode:
        print(json.dumps({"error": message}, indent=2))
    else:
        print(f"Error: {message}", file=sys.stderr)
