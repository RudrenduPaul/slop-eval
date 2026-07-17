# Concepts

## The scoring pipeline

Both the npm and PyPI packages run the same pipeline (TypeScript:
`src/scorer/composite.ts` + `src/sources/*`; Python:
`slop_eval/scorer.py` + `slop_eval/sources/*`):

```
--url or --screenshot
        |
        v
  LLMJudgeSource              ScreenshotDiffSource (v0.1 stub,
  (Anthropic API call,          always returns one "not_scored"
   content-hash cached)         finding -- no corpus exists yet)
        |                              |
        +---------------+--------------+
                         v
              composite scorer: average every
              non-"not_scored" 0-10 score,
              scale to 0-100
                         v
              report writer (human text or --json)
```

A composite result always comes back as a structured value, never a raised
exception for a "no data" case -- `ScreenshotDiffSource` returns a
`not_scored` finding instead of failing, so the report writer can surface
"this dimension isn't scored yet" honestly instead of silently omitting it.

## The rubric

Every score is graded against a versioned, public rubric file
(`slop_eval/rubric/v1.json`, ported byte-for-byte from the npm package's
`src/rubric/v1.json`). v1 has three categories, each scored 0-10 by the
LLM judge with a required, specific evidence string:

| Category | What it evaluates |
| --- | --- |
| `layout-novelty` | Does the page's structural layout (section ordering, grid/column structure, hero/nav/footer arrangement) show a distinctive composition, or does it match a generic, ubiquitous template (hero + 3-feature-cards + testimonial + footer) seen across many AI-generated sites? |
| `visual-identity-distinctiveness` | Does the color palette, typography, and iconography feel like a deliberate, specific brand identity, or does it default to common AI-generated visual tells (a purple/indigo gradient on white, Inter/system-font body text, generic line icons)? |
| `component-pattern-novelty` | Do individual components (cards, buttons, forms, navigation) show original interaction/visual patterns, or do they reproduce default component-library output with no customization? |

A rubric version is never edited in place -- a change ships as a new
`slop_eval/rubric/v2.json` (once one exists) so a historical score always
records which rubric version produced it. Pin a specific version with
`--rubric`.

## How the LLM judge is called

`LLMJudgeSource` (`slop_eval/sources/llm_judge.py`) calls the Anthropic API
via the official `anthropic` Python SDK's `messages.create()`, with
`tool_choice` locked to a `submit_slop_scores` tool schema -- the model's
response comes back as a `tool_use` content block with structured JSON
input, rather than free text that would need to be parsed out of a chat
reply. This is the same forced-tool-call pattern the TypeScript original
uses, ported directly rather than reimplemented differently.

- **`--screenshot`** (preferred): the image is read, base64-encoded, and
  sent to the judge as an `image` content block -- a real rendered view of
  the UI.
- **`--url`** (v0.1 fallback): no headless browser is bundled to render
  the page into a screenshot. The raw HTML/text response is fetched
  (stdlib `urllib`, capped at 10MB via `Content-Length` and a 30-second
  timeout, both overridable via `SLOP_EVAL_FETCH_TIMEOUT_MS`) and given to
  the judge as text, truncated to 20,000 characters. The judge can reason
  about markup, inline styles, and copy, but not the actual rendered
  visual layout -- `--screenshot` is the stronger signal.

Every real judge call is wrapped through the content-hash cache
(`slop_eval/cache.py`): identical input (same screenshot bytes, or the
same URL plus fetched text) never triggers a second API call. This is a
correctness guarantee, not just a cost optimization -- without it,
re-running slop-eval against an unchanged PR could flap a CI gate on the
LLM's own run-to-run variance. Cache entries default to
`.slop-eval-cache/<sha256-hash>.json` under the current working directory.

## The composite score

`score_composite()` (`slop_eval/scorer.py`) runs every configured
`RuleSource`, flattens their findings, and averages every finding whose
`status` is not `"not_scored"`, scaled from a 0-10 per-category average to
a 0-100 composite. If every finding is `not_scored` (or there are no
sources at all), the composite score is `0` -- there's nothing real to
average, and `0` is a safer default than a fabricated high score when a
caller applies `--fail-below`.

**Note on execution order:** the TypeScript original runs its
`RuleSource`s concurrently via `Promise.all`. This Python port runs them
sequentially, in list order. With exactly two v0.1 sources, the result
(same findings, same order, same composite score) is identical either way.

## The `RuleSource` plugin interface

```python
class RuleSource(Protocol):
    name: str
    def score(self, score_input: ScoreInput) -> List[RuleFinding]: ...
```

Every scoring source -- `LLMJudgeSource`, the `ScreenshotDiffSource` stub,
and any future addition (a deterministic rule-catalog adapter, a second
LLM provider) -- implements this same two-member contract. The composite
scorer treats every source identically: run it, collect its findings, fold
them into the composite. This exists from the Python port's first commit,
mirroring the TypeScript original's own reasoning: the domain genuinely
has more than one integration target over time, so the plugin boundary is
cheaper to ship now than to retrofit later. See
[examples/03-agent-native-json](../examples/03-agent-native-json/) for a
real, runnable custom `RuleSource`.

## What a score means (and doesn't)

A slop-eval score is a heuristic quality signal from one LLM's read of
your UI against a stated rubric. It is not a certification that something
is or isn't AI-generated, and a clean score doesn't mean the UI is good by
every measure, only that this rubric, at this version, didn't flag it.
Every report (`--json` and human-readable) embeds this disclaimer verbatim.
