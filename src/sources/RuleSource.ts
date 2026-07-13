/**
 * RuleSource is the plugin interface every scoring source implements --
 * whether it's slop-eval's own LLM-judge, a future deterministic rule
 * catalog adapter (e.g. Impeccable's Slop, once license-cleared), or a
 * corpus-backed screenshot-diff engine. The composite scorer (see
 * src/scorer/composite.ts) treats every RuleSource identically: run it,
 * collect its RuleFinding[], fold it into one composite score.
 *
 * This interface exists from the first commit -- not because v0.1 ships
 * multiple sources (it ships one real source plus one documented stub),
 * but because the domain genuinely has more than one integration target
 * over time (multiple rule catalogs, multiple LLM providers backing the
 * judge). Retrofitting a plugin boundary after the fact is more expensive
 * than shipping it now.
 */

/** Status of an individual rubric-category finding. */
export type RuleFindingStatus = 'pass' | 'flag' | 'not_scored';

/**
 * One scored rubric category from one RuleSource.
 *
 * `evidence` must always be a specific, cited reason -- e.g. "matches a
 * hero+3-card+footer pattern also seen in the fixture corpus", never a
 * generic "layout could be more original." A finding with no citation is
 * not shippable (see [redacted] anti-sycophancy rule #2).
 */
export interface RuleFinding {
  /** Stable identifier for this specific rule, e.g. "llm-judge.layout-novelty". */
  ruleId: string;
  /** Human-readable rubric category name, e.g. "Layout novelty". */
  category: string;
  /** 0-10. Meaningless when status is 'not_scored' -- callers must exclude those from any average. */
  score: number;
  /** Specific, cited reason for the score -- never a generic statement. */
  evidence: string;
  status: RuleFindingStatus;
}

/** Input to a RuleSource. Callers provide a URL or a screenshot path -- not both are required, but at least one is. */
export interface ScoreInput {
  url?: string;
  screenshotPath?: string;
}

/** A pluggable scoring source. Implementations must never throw for "no data" -- return a 'not_scored' finding instead. */
export interface RuleSource {
  /** Stable, human-readable name for this source, e.g. "llm-judge", "screenshot-diff-vs-corpus". */
  name: string;
  score(input: ScoreInput): Promise<RuleFinding[]>;
}
