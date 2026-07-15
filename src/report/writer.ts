/**
 * Report writer -- turns a composite scoring result into either a
 * human-readable terminal report or a structured JSON object, depending on
 * the caller's --json flag.
 *
 * Every human-readable report must state plainly that the score is a
 * heuristic quality signal, not a certification -- never implying
 * "not AI-generated" or "definitely slop."
 */

import type { CompositeResult } from '../scorer/composite';
import type { RuleFinding } from '../sources/RuleSource';

export interface JsonReport {
  target: string;
  rubric: string;
  compositeScore: number;
  findings: RuleFinding[];
  summary: { pass: number; flagged: number; notScored: number };
  disclaimer: string;
}

const DISCLAIMER =
  'This score is a heuristic quality signal from an LLM judge, not a certification. ' +
  'It does not mean the UI "is" or "is not" AI-generated, and it is not a guarantee of ' +
  'quality in either direction.';

function summarize(findings: RuleFinding[]): { pass: number; flagged: number; notScored: number } {
  return {
    pass: findings.filter((f) => f.status === 'pass').length,
    flagged: findings.filter((f) => f.status === 'flag').length,
    notScored: findings.filter((f) => f.status === 'not_scored').length,
  };
}

/** Builds the structured JSON report object (used both by --json mode and by the GitHub Action). */
export function buildJsonReport(
  result: CompositeResult,
  target: string,
  rubricName: string,
): JsonReport {
  return {
    target,
    rubric: rubricName,
    compositeScore: Math.round(result.compositeScore),
    findings: result.findings,
    summary: summarize(result.findings),
    disclaimer: DISCLAIMER,
  };
}

/** Renders the same data as a human-readable terminal report. */
export function renderHumanReport(
  result: CompositeResult,
  target: string,
  rubricName: string,
): string {
  const { pass, flagged, notScored } = summarize(result.findings);
  const lines: string[] = [];

  lines.push(`slop-eval v0.1 -- AI-Slop Quality Score (rubric: ${rubricName})`);
  lines.push(`Target: ${target}`);
  lines.push('');
  lines.push(`Score: ${Math.round(result.compositeScore)}/100`);
  lines.push('');

  for (const finding of result.findings) {
    if (finding.status === 'not_scored') {
      lines.push(`[NOT SCORED] ${finding.category}`);
      lines.push(`  ${finding.evidence}`);
    } else {
      const tag = finding.status === 'pass' ? '[PASS] ' : '[FLAG] ';
      lines.push(`${tag} ${finding.category}: ${finding.score}/10`);
      lines.push(`  ${finding.evidence}`);
    }
    lines.push('');
  }

  lines.push(`Summary: ${pass} pass, ${flagged} flagged, ${notScored} not scored`);
  lines.push('');
  lines.push(DISCLAIMER);

  return lines.join('\n');
}

/** Prints the report to stdout in the requested mode. Does not mix JSON and human-readable text. */
export function printReport(
  result: CompositeResult,
  target: string,
  rubricName: string,
  jsonMode: boolean,
): void {
  if (jsonMode) {
    // eslint-disable-next-line no-console -- this is the tool's structured stdout output, not a debug log
    console.log(JSON.stringify(buildJsonReport(result, target, rubricName), null, 2));
  } else {
    // eslint-disable-next-line no-console -- this is the tool's primary stdout output, not a debug log
    console.log(renderHumanReport(result, target, rubricName));
  }
}
