"""
RuleSource is the plugin interface every scoring source implements -- the
Python port of src/sources/RuleSource.ts. Whether it's slop-eval's own
LLM judge, a future deterministic rule catalog adapter, or a corpus-backed
screenshot-diff engine, the composite scorer (see slop_eval/scorer.py)
treats every RuleSource identically: run it, collect its findings, fold
them into one composite score.

This interface exists from the first commit of the Python port, mirroring
the TypeScript original's own reasoning: the domain genuinely has more than
one integration target over time (multiple rule catalogs, multiple LLM
providers backing the judge), so the plugin boundary is cheaper to ship now
than to retrofit later.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, Protocol

RuleFindingStatus = Literal["pass", "flag", "not_scored"]


@dataclass
class RuleFinding:
    """
    One scored rubric category from one RuleSource.

    `evidence` must always be a specific, cited reason -- e.g. "matches a
    hero+3-card+footer pattern also seen in the fixture corpus", never a
    generic "layout could be more original." A finding with no citation is
    not a valid result (ported from the same rule in RuleSource.ts).
    """

    rule_id: str
    """Stable identifier for this specific rule, e.g. "llm-judge.layout-novelty"."""
    category: str
    """Human-readable rubric category name, e.g. "Layout novelty"."""
    score: float
    """0-10. Meaningless when status is 'not_scored' -- callers must exclude those from any average."""
    evidence: str
    """Specific, cited reason for the score -- never a generic statement."""
    status: RuleFindingStatus


@dataclass
class ScoreInput:
    """Input to a RuleSource. Exactly one of url/screenshot_path is expected to be set by callers."""

    url: Optional[str] = None
    screenshot_path: Optional[str] = None


class RuleSource(Protocol):
    """A pluggable scoring source. Implementations must never raise for "no data" -- return a 'not_scored' finding instead."""

    name: str

    def score(self, score_input: ScoreInput) -> List[RuleFinding]: ...
