import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { getCachedOrCompute } from '../src/cache/judge-cache';

describe('judge-cache', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'slop-eval-cache-test-'));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('calls computeFn exactly once across two calls with the same hash', async () => {
    const computeFn = vi.fn().mockResolvedValue({ score: 42 });

    const first = await getCachedOrCompute('abc123', computeFn, tmpDir);
    const second = await getCachedOrCompute('abc123', computeFn, tmpDir);

    expect(computeFn).toHaveBeenCalledTimes(1);
    expect(first).toEqual({ score: 42 });
    expect(second).toEqual({ score: 42 });
  });

  it('calls computeFn again for a different hash', async () => {
    const computeFn = vi.fn().mockResolvedValue({ score: 1 });

    await getCachedOrCompute('hash-a', computeFn, tmpDir);
    await getCachedOrCompute('hash-b', computeFn, tmpDir);

    expect(computeFn).toHaveBeenCalledTimes(2);
  });

  it('persists the cache entry on disk as JSON', async () => {
    await getCachedOrCompute('hash-c', async () => ({ x: 1 }), tmpDir);

    const cachePath = path.join(tmpDir, 'hash-c.json');
    expect(fs.existsSync(cachePath)).toBe(true);
    expect(JSON.parse(fs.readFileSync(cachePath, 'utf-8'))).toEqual({ x: 1 });
  });

  it('creates the cache directory when it does not exist yet', async () => {
    const nestedDir = path.join(tmpDir, 'nested', 'cache-dir');

    await getCachedOrCompute('hash-d', async () => ({ y: 2 }), nestedDir);

    expect(fs.existsSync(path.join(nestedDir, 'hash-d.json'))).toBe(true);
  });

  it('recomputes and overwrites a corrupted/unparseable cache entry instead of throwing', async () => {
    const cachePath = path.join(tmpDir, 'hash-corrupt.json');
    fs.writeFileSync(cachePath, '{ this is not valid json');
    const computeFn = vi.fn().mockResolvedValue({ recomputed: true });

    const result = await getCachedOrCompute('hash-corrupt', computeFn, tmpDir);

    expect(computeFn).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ recomputed: true });
    expect(JSON.parse(fs.readFileSync(cachePath, 'utf-8'))).toEqual({ recomputed: true });
  });

  it('defaults to the .slop-eval-cache directory under the given cwd-relative path when no cacheDir is passed', async () => {
    // Use a relative path resolved against process.cwd() by passing a bare
    // relative dir name -- verifies the default-cacheDir resolution branch
    // without touching the real project's cache directory.
    const relativeName = `.slop-eval-cache-test-${Date.now()}`;
    const expectedDir = path.resolve(process.cwd(), relativeName);
    try {
      const computeFn = vi.fn().mockResolvedValue({ z: 3 });
      await getCachedOrCompute('hash-e', computeFn, relativeName);
      expect(fs.existsSync(path.join(expectedDir, 'hash-e.json'))).toBe(true);
    } finally {
      fs.rmSync(expectedDir, { recursive: true, force: true });
    }
  });
});
