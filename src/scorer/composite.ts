/**
 * Composite scorer -- combines every RuleSource's findings into one 0-100
 * score and a flat findings list for the report writer.
 *
 * This module (along with LLMJudgeSource) directly produces the CI-gate
 * verdict, so it carries a 95%+ test coverage requirement -- a bug in this
 * averaging logic is a wrong CI decision, not just a cosmetic report bug.
 */

import type { RuleFinding, RuleSource, ScoreInput } from '../sources/RuleSource';

export interface CompositeResult {
  /** 0-100. Average of every non-'not_scored' finding's 0-10 score, scaled to 0-100. */
  compositeScore: number;
  /** Flattened findings from every source, in source order. */
  findings: RuleFinding[];
}

/**
 * Runs every RuleSource against `input` in parallel, flattens their
 * RuleFinding[] results, and computes a composite 0-100 score as the average
 * of all non-'not_scored' findings' 0-10 scores, scaled to 0-100.
 *
 * 'not_scored' findings are always excluded from the average (their `score`
 * field is meaningless -- see RuleFinding's docstring) but always included in
 * the returned `findings` list, since the report writer must surface them
 * (e.g. ScreenshotDiffSource's "no corpus yet" stub finding).
 *
 * If every finding is 'not_scored' (no source produced a real score), or no
 * source produced any finding at all, `compositeScore` is 0 -- there is
 * nothing to average, and 0 is a safer default than a fabricated high score
 * when a caller applies `--fail-below`.
 */
export async function scoreComposite(
  sources: RuleSource[],
  input: ScoreInput,
): Promise<CompositeResult> {
  const perSourceFindings = await Promise.all(sources.map((source) => source.score(input)));
  const findings = perSourceFindings.flat();

  const scorable = findings.filter((f) => f.status !== 'not_scored');
  const compositeScore =
    scorable.length === 0
      ? 0
      : (scorable.reduce((sum, f) => sum + f.score, 0) / scorable.length) * 10;

  return { compositeScore, findings };
}
