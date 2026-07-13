import { describe, it, expect } from 'vitest';
import { ScreenshotDiffSource } from '../src/sources/ScreenshotDiffSource';

describe('ScreenshotDiffSource (v0.1 stub)', () => {
  it('always returns exactly one not_scored finding regardless of input', async () => {
    const source = new ScreenshotDiffSource();

    const fromScreenshot = await source.score({ screenshotPath: 'whatever.png' });
    const fromUrl = await source.score({ url: 'https://example.com' });
    const fromEmpty = await source.score({});

    for (const findings of [fromScreenshot, fromUrl, fromEmpty]) {
      expect(findings).toHaveLength(1);
      expect(findings[0].status).toBe('not_scored');
      expect(findings[0].category).toBe('screenshot-diff-vs-corpus');
      expect(findings[0].evidence).toMatch(/no.*corpus/i);
    }
  });

  it('exposes a stable source name', () => {
    const source = new ScreenshotDiffSource();
    expect(source.name).toBe('screenshot-diff-vs-corpus');
  });
});
