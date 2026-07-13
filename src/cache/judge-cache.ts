/**
 * Content-hash cache for LLM-judge scores. Identical input (same screenshot
 * bytes, or same URL+fetched-content bytes) must never trigger a second LLM
 * API call -- this is a correctness requirement (see CLAUDE.md's "Judge-cache
 * correctness" engineering standard), not just a cost optimization: without
 * it, re-running slop-eval against an unchanged PR could flap a CI gate if
 * the LLM's output has any run-to-run variance.
 *
 * Cache storage is a local file cache by default (`.slop-eval-cache/<hash>.json`
 * relative to the current working directory), pluggable for a future hosted
 * cache in the paid tier -- callers that need a different location (tests,
 * a future remote cache) pass `cacheDir` explicitly.
 */

import * as fs from 'fs';
import * as path from 'path';

export const DEFAULT_CACHE_DIR = '.slop-eval-cache';

/**
 * Look up a cached value for `hash`; if absent, call `computeFn`, persist the
 * result, and return it. `computeFn` is guaranteed to run at most once per
 * hash across repeated calls against the same cache directory (assuming no
 * concurrent writers) -- this is asserted directly in
 * test/judge-cache.test.ts by mocking computeFn and counting invocations.
 *
 * @param hash content hash identifying the input (see LLMJudgeSource for how
 *   it's derived from screenshot bytes or URL+fetched content).
 * @param computeFn produces the value on a cache miss. Only called when no
 *   cached value exists.
 * @param cacheDir override the cache directory (defaults to
 *   `.slop-eval-cache` under the current working directory). Exposed mainly
 *   so tests don't pollute the real project cache.
 */
export async function getCachedOrCompute<T>(
  hash: string,
  computeFn: () => Promise<T>,
  cacheDir: string = DEFAULT_CACHE_DIR,
): Promise<T> {
  const resolvedDir = path.isAbsolute(cacheDir) ? cacheDir : path.resolve(process.cwd(), cacheDir);
  const cachePath = path.join(resolvedDir, `${hash}.json`);

  if (fs.existsSync(cachePath)) {
    const raw = fs.readFileSync(cachePath, 'utf-8');
    return JSON.parse(raw) as T;
  }

  const result = await computeFn();

  fs.mkdirSync(resolvedDir, { recursive: true });
  // Write to a temp file then rename so a crash mid-write never leaves a
  // half-written, unparseable cache entry behind.
  const tmpPath = `${cachePath}.tmp-${process.pid}-${Date.now()}`;
  fs.writeFileSync(tmpPath, JSON.stringify(result, null, 2));
  fs.renameSync(tmpPath, cachePath);

  return result;
}
