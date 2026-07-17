#!/usr/bin/env python3
"""
03 -- agent-native JSON + a custom RuleSource.

Demonstrates two things at once, and needs no ANTHROPIC_API_KEY to run:

1. The composable `RuleSource` plugin interface (`slop_eval.RuleSource`,
   `slop_eval.RuleFinding`) is a real, usable extension point, not just an
   internal abstraction -- this defines a small third-party-style
   RuleSource (a naive "does the page mention any of a fixed list of
   generic buzzwords" text check) and runs it alongside the bundled
   ScreenshotDiffSource stub, with zero changes needed to score_composite()
   or the report writer.
2. `build_json_report()` -- the same schema slop-eval's `--json` CLI mode
   emits -- for an agent framework that wants to consume a structured
   result in-process instead of shelling out to the CLI and parsing stdout.

Run:
    python3 examples/03-agent-native-json/agent_report.py
"""
import json

from slop_eval import RuleFinding, ScoreInput, ScreenshotDiffSource, build_json_report, score_composite

GENERIC_BUZZWORDS = ["revolutionize", "seamless", "cutting-edge", "unleash", "empower"]


class BuzzwordTextSource:
    """
    A minimal, fully local RuleSource: flags generic marketing buzzwords in
    a page's text content. No network call, no API key -- just a real
    implementation of the `name` + `score()` contract every RuleSource
    (including the bundled LLMJudgeSource) implements.
    """

    name = "buzzword-text-check"

    def score(self, score_input: ScoreInput):
        text = (score_input.url or "") + " sample page copy: seamless, cutting-edge onboarding experience"
        hits = [word for word in GENERIC_BUZZWORDS if word in text.lower()]

        if not hits:
            return [
                RuleFinding(
                    rule_id="buzzword-text-check.no-hits",
                    category="Generic buzzword usage",
                    score=10,
                    evidence="No generic marketing buzzwords found in the page text.",
                    status="pass",
                )
            ]

        return [
            RuleFinding(
                rule_id="buzzword-text-check.hits",
                category="Generic buzzword usage",
                score=max(0, 10 - 2 * len(hits)),
                evidence=f"Found {len(hits)} generic buzzword(s): {', '.join(hits)}.",
                status="flag",
            )
        ]


def main() -> None:
    sources = [BuzzwordTextSource(), ScreenshotDiffSource()]
    result = score_composite(sources, ScoreInput(url="https://example.com"))

    report = build_json_report(result, "https://example.com", "v1")

    print("--- agent-native JSON report (same schema as `slop-eval score --json`) ---")
    print(json.dumps(report, indent=2))
    print()
    print(
        f"A calling agent can now branch programmatically, e.g.: "
        f"would_flag = {any(f['status'] == 'flag' for f in report['findings'])}"
    )


if __name__ == "__main__":
    main()
