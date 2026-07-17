"""
Composite scorer -- combines every RuleSource's findings into one 0-100
score and a flat findings list for the report writer. Ported from
src/scorer/composite.ts.

This module (along with sources/llm_judge.py) directly produces the CI-gate
verdict -- a bug in this averaging logic is a wrong CI decision, not just a
cosmetic report bug, so it carries the same high-coverage bar the
TypeScript original sets for composite.ts.

Note on parallelism: the TypeScript original runs every RuleSource
concurrently via Promise.all, since Node's I/O is naturally async. This
Python port runs sources sequentially in list order -- v0.1 ships exactly
two sources (LLMJudgeSource, ScreenshotDiffSource), and the composite result
(same findings, same order, same score) is identical either way; sequential
execution is simply the simpler implementation for that source count.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .sources.base import RuleFinding, RuleSource, ScoreInput


@dataclass
class CompositeResult:
    composite_score: float
    """0-100. Average of every non-'not_scored' finding's 0-10 score, scaled to 0-100."""
    findings: List[RuleFinding]
    """Flattened findings from every source, in source order."""


def score_composite(sources: List[RuleSource], score_input: ScoreInput) -> CompositeResult:
    """
    Runs every RuleSource against `score_input` (in source-list order),
    flattens their findings, and computes a composite 0-100 score as the
    average of all non-'not_scored' findings' 0-10 scores, scaled to 0-100.

    'not_scored' findings are always excluded from the average (their
    `score` field is meaningless) but always included in the returned
    `findings` list, since the report writer must surface them (e.g.
    ScreenshotDiffSource's "no corpus yet" stub finding).

    If every finding is 'not_scored', or no source produced any finding at
    all, `compositeScore` is 0 -- there is nothing to average, and 0 is a
    safer default than a fabricated high score when a caller applies
    --fail-below.
    """
    findings: List[RuleFinding] = []
    for source in sources:
        findings.extend(source.score(score_input))

    scorable = [f for f in findings if f.status != "not_scored"]
    if not scorable:
        composite_score = 0.0
    else:
        composite_score = (sum(f.score for f in scorable) / len(scorable)) * 10

    return CompositeResult(composite_score=composite_score, findings=findings)
