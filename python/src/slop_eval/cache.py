"""
Content-hash cache for LLM-judge scores. Ported from src/cache/judge-cache.ts.
Identical input (same screenshot bytes, or same URL+fetched-content bytes)
must never trigger a second LLM API call -- this is a correctness
requirement, not just a cost optimization: without it, re-running slop-eval
against an unchanged PR could flap a CI gate if the LLM's output has any
run-to-run variance.

Cache storage is a local file cache by default (`.slop-eval-cache/<hash>.json`
relative to the current working directory), pluggable for a future hosted
cache, the same as the TypeScript original -- callers that need a different
location (tests, a future remote cache) pass `cache_dir` explicitly.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, TypeVar

DEFAULT_CACHE_DIR = ".slop-eval-cache"

T = TypeVar("T")


def get_cached_or_compute(content_hash: str, compute_fn: Callable[[], T], cache_dir: str = DEFAULT_CACHE_DIR) -> T:
    """
    Look up a cached value for `content_hash`; if absent, call `compute_fn`,
    persist the result, and return it. `compute_fn` is guaranteed to run at
    most once per hash across repeated calls against the same cache
    directory (assuming no concurrent writers) -- asserted directly in
    tests/test_cache.py by using a counting stub in place of compute_fn.
    """
    resolved_dir = Path(cache_dir) if os.path.isabs(cache_dir) else Path.cwd() / cache_dir
    cache_path = resolved_dir / f"{content_hash}.json"

    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            # A cache entry that exists but can't be read/parsed (truncated
            # by a crash that raced the temp-file-then-rename write,
            # corrupted on disk, or left over from an incompatible earlier
            # schema version) must not permanently break every future run
            # against this hash -- treat it as a miss and recompute rather
            # than raising, and fall through below to overwrite it with a
            # good entry.
            print(
                f"slop-eval: cache entry at {cache_path} is unreadable or corrupted ({err}) -- "
                "recomputing instead of failing.",
                file=sys.stderr,
            )

    result = compute_fn()

    resolved_dir.mkdir(parents=True, exist_ok=True)
    # Write to a temp file then rename so a crash mid-write never leaves a
    # half-written, unparseable cache entry behind.
    tmp_path = resolved_dir / f"{content_hash}.json.tmp-{os.getpid()}-{int(time.time() * 1000)}"
    tmp_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tmp_path.replace(cache_path)

    return result
