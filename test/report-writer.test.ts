import { describe, it, expect } from 'vitest';
import { buildJsonReport, renderHumanReport } from '../src/report/writer';
import type { CompositeResult } from '../src/scorer/composite';

const sampleResult: CompositeResult = {
  compositeScore: 61.6,
  findings: [
    {
      ruleId: 'llm-judge.layout-novelty',
      category: 'Layout novelty',
      score: 4,
      evidence: 'Matches a hero+3-card+footer pattern common in template output.',
      status: 'flag',
    },
    {
      ruleId: 'llm-judge.component-pattern-novelty',
      category: 'Component-pattern novelty',
      score: 7,
      evidence: 'Cards use a custom asymmetric hover reveal, not a stock pattern.',
      status: 'pass',
    },
    {
      ruleId: 'screenshot-diff.no-corpus-v0.1',
      category: 'screenshot-diff-vs-corpus',
      score: 0,
      evidence: 'No corpus exists yet in v0.1.',
      status: 'not_scored',
    },
  ],
};

describe('report writer', () => {
  it('buildJsonReport produces the documented schema with a rounded score and summary counts', () => {
    const report = buildJsonReport(sampleResult, 'https://example.com', 'v1');

    expect(report.target).toBe('https://example.com');
    expect(report.rubric).toBe('v1');
    expect(report.compositeScore).toBe(62);
    expect(report.summary).toEqual({ pass: 1, flagged: 1, notScored: 1 });
    expect(report.findings).toHaveLength(3);
    expect(report.disclaimer).toMatch(/heuristic/i);
    expect(report.disclaimer).toMatch(/not a certification/i);
  });

  it('renderHumanReport includes the score, per-finding breakdown, and the disclaimer', () => {
    const text = renderHumanReport(sampleResult, 'https://example.com', 'v1');

    expect(text).toContain('Target: https://example.com');
    expect(text).toContain('Score: 62/100');
    expect(text).toContain('[FLAG]');
    expect(text).toContain('Layout novelty: 4/10');
    expect(text).toContain('[PASS]');
    expect(text).toContain('Component-pattern novelty: 7/10');
    expect(text).toContain('[NOT SCORED] screenshot-diff-vs-corpus');
    expect(text).toContain('Summary: 1 pass, 1 flagged, 1 not scored');
    expect(text).toMatch(/heuristic quality signal/i);
  });

  it('renderHumanReport never omits evidence for a finding', () => {
    const text = renderHumanReport(sampleResult, 'https://example.com', 'v1');
    for (const finding of sampleResult.findings) {
      expect(text).toContain(finding.evidence);
    }
  });
});
