"""Ported from test/judge-cache.test.ts."""
import json
from pathlib import Path

import pytest

from slop_eval.cache import get_cached_or_compute


@pytest.fixture()
def tmp_cache_dir(tmp_path):
    return str(tmp_path / "cache")


def test_calls_compute_fn_exactly_once_across_two_calls_with_same_hash(tmp_cache_dir):
    calls = []

    def compute_fn():
        calls.append(1)
        return {"score": 42}

    first = get_cached_or_compute("abc123", compute_fn, tmp_cache_dir)
    second = get_cached_or_compute("abc123", compute_fn, tmp_cache_dir)

    assert len(calls) == 1
    assert first == {"score": 42}
    assert second == {"score": 42}


def test_calls_compute_fn_again_for_a_different_hash(tmp_cache_dir):
    calls = []

    def compute_fn():
        calls.append(1)
        return {"score": 1}

    get_cached_or_compute("hash-a", compute_fn, tmp_cache_dir)
    get_cached_or_compute("hash-b", compute_fn, tmp_cache_dir)

    assert len(calls) == 2


def test_persists_the_cache_entry_on_disk_as_json(tmp_cache_dir):
    get_cached_or_compute("hash-c", lambda: {"x": 1}, tmp_cache_dir)

    cache_path = Path(tmp_cache_dir) / "hash-c.json"
    assert cache_path.exists()
    assert json.loads(cache_path.read_text()) == {"x": 1}


def test_creates_the_cache_directory_when_it_does_not_exist_yet(tmp_path):
    nested_dir = str(tmp_path / "nested" / "cache-dir")

    get_cached_or_compute("hash-d", lambda: {"y": 2}, nested_dir)

    assert (Path(nested_dir) / "hash-d.json").exists()


def test_recomputes_and_overwrites_a_corrupted_cache_entry_instead_of_raising(tmp_cache_dir):
    cache_dir = Path(tmp_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "hash-corrupt.json"
    cache_path.write_text("{ this is not valid json")

    calls = []

    def compute_fn():
        calls.append(1)
        return {"recomputed": True}

    result = get_cached_or_compute("hash-corrupt", compute_fn, tmp_cache_dir)

    assert len(calls) == 1
    assert result == {"recomputed": True}
    assert json.loads(cache_path.read_text()) == {"recomputed": True}


def test_defaults_to_a_cwd_relative_directory_when_a_relative_cache_dir_is_passed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    relative_name = ".slop-eval-cache-test"
    expected_dir = tmp_path / relative_name

    get_cached_or_compute("hash-e", lambda: {"z": 3}, relative_name)

    assert (expected_dir / "hash-e.json").exists()
