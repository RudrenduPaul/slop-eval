"""
ScreenshotDiffSource -- v0.1 STUB, ported verbatim in intent from
src/sources/ScreenshotDiffSource.ts.

Scope decision (carried over from the TypeScript original): this source
ships as a real RuleSource implementation, but with no corpus and no real
diff algorithm behind it in v0.1. Hand-seeding an arbitrary corpus now
would produce an unvalidated, made-up signal -- worse than no signal.
Corpus-backed comparison is real v0.2 scope once genuine usage produces
labeled examples worth diffing against.

This is intentional, documented scope -- not a placeholder for a forgotten
feature. It always returns exactly one 'not_scored' finding explaining why,
so the composite scorer and report writer can surface it honestly instead
of silently omitting a rubric dimension users might expect.
"""
from __future__ import annotations

from typing import List

from .base import RuleFinding, ScoreInput


class ScreenshotDiffSource:
    name = "screenshot-diff-vs-corpus"

    def score(self, score_input: ScoreInput) -> List[RuleFinding]:
        return [
            RuleFinding(
                rule_id="screenshot-diff.no-corpus-v0.1",
                category="screenshot-diff-vs-corpus",
                score=0,
                evidence=(
                    "slop-eval v0.1 ships this RuleSource as an interface only -- there is no "
                    "seeded comparison corpus yet, so no real screenshot-diff score can be "
                    "produced. This is documented v0.1 scope, not a "
                    "bug: a hand-seeded, unvalidated corpus would produce a less honest signal "
                    'than reporting "not scored." Corpus-backed diffing against real, labeled '
                    "examples is planned for v0.2."
                ),
                status="not_scored",
            )
        ]
