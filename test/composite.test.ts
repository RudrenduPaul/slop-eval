import { describe, it, expect } from 'vitest';
import { scoreComposite } from '../src/scorer/composite';
import type { RuleSource, RuleFinding, ScoreInput } from '../src/sources/RuleSource';

function fakeSource(name: string, findings: RuleFinding[]): RuleSource {
  return {
    name,
    score: async (_input: ScoreInput) => findings,
  };
}

describe('scoreComposite', () => {
  it('averages non-not_scored findings and scales 0-10 to 0-100', async () => {
    const source = fakeSource('fake', [
      { ruleId: 'a', category: 'A', score: 8, evidence: 'e', status: 'pass' },
      { ruleId: 'b', category: 'B', score: 4, evidence: 'e', status: 'flag' },
    ]);

    const result = await scoreComposite([source], {});

    expect(result.compositeScore).toBe(60);
    expect(result.findings).toHaveLength(2);
  });

  it('excludes not_scored findings from the average but keeps them in the findings list', async () => {
    const source = fakeSource('fake', [
      { ruleId: 'a', category: 'A', score: 10, evidence: 'e', status: 'pass' },
      { ruleId: 'b', category: 'B', score: 0, evidence: 'no corpus', status: 'not_scored' },
    ]);

    const result = await scoreComposite([source], {});

    expect(result.compositeScore).toBe(100);
    expect(result.findings).toHaveLength(2);
    expect(result.findings.some((f) => f.status === 'not_scored')).toBe(true);
  });

  it('returns 0 when every finding is not_scored', async () => {
    const source = fakeSource('fake', [
      { ruleId: 'a', category: 'A', score: 0, evidence: 'no corpus', status: 'not_scored' },
    ]);

    const result = await scoreComposite([source], {});

    expect(result.compositeScore).toBe(0);
  });

  it('returns 0 and an empty findings list when there are no sources at all', async () => {
    const result = await scoreComposite([], {});

    expect(result.compositeScore).toBe(0);
    expect(result.findings).toEqual([]);
  });

  it('runs multiple sources in parallel and flattens their findings in source order', async () => {
    const s1 = fakeSource('s1', [
      { ruleId: 'a', category: 'A', score: 10, evidence: 'e', status: 'pass' },
    ]);
    const s2 = fakeSource('s2', [
      { ruleId: 'b', category: 'B', score: 0, evidence: 'e', status: 'flag' },
    ]);

    const result = await scoreComposite([s1, s2], {});

    expect(result.findings.map((f) => f.ruleId)).toEqual(['a', 'b']);
    expect(result.compositeScore).toBe(50);
  });

  it('rounds to a clean fraction for uneven averages', async () => {
    const source = fakeSource('fake', [
      { ruleId: 'a', category: 'A', score: 7, evidence: 'e', status: 'pass' },
      { ruleId: 'b', category: 'B', score: 5, evidence: 'e', status: 'flag' },
      { ruleId: 'c', category: 'C', score: 4, evidence: 'e', status: 'flag' },
    ]);

    const result = await scoreComposite([source], {});

    // (7 + 5 + 4) / 3 = 5.333... * 10 = 53.33...
    expect(result.compositeScore).toBeCloseTo(53.33, 1);
  });
});
