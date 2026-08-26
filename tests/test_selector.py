"""Tests for pipeline.tasks.selector."""

from __future__ import annotations

from pipeline.tasks.selector import SelectableCandidate, select


def _cand(id_: str, source: str, score: float, module: str = "", files=()):
    return SelectableCandidate(
        id=id_,
        source=source,
        score=score,
        module=module,
        files_touched=set(files),
    )


def test_selects_exactly_total_when_pool_large():
    pool = (
        [_cand(f"h{i}", "history", 0.9 - i * 0.01,
               module=f"mod_h{i % 4}", files=[f"h{i}.py"])
         for i in range(10)]
        + [_cand(f"e{i}", "excision", 0.8 - i * 0.01,
                 module=f"mod_e{i % 3}", files=[f"e{i}.py"])
           for i in range(10)]
    )
    chosen = select(pool, total=10)
    assert len(chosen) == 10


def test_min_history_enforced():
    pool = (
        [_cand(f"h{i}", "history", 0.5, module=f"h{i}", files=[f"h{i}.py"])
         for i in range(5)]
        + [_cand(f"e{i}", "excision", 0.9, module=f"e{i}", files=[f"e{i}.py"])
           for i in range(20)]
    )
    chosen = select(pool, total=10, min_history=4)
    history_count = sum(1 for c in chosen if c.source == "history")
    assert history_count >= 4


def test_max_excision_enforced():
    pool = [
        _cand(f"e{i}", "excision", 1.0 - i * 0.001,
              module=f"m{i}", files=[f"e{i}.py"])
        for i in range(30)
    ]
    chosen = select(pool, total=10, min_history=0, max_excision=4)
    assert sum(1 for c in chosen if c.source == "excision") == 4


def test_max_net_new_enforced():
    pool = [
        _cand(f"n{i}", "net_new", 1.0, module=f"m{i}", files=[f"n{i}.py"])
        for i in range(10)
    ] + [
        _cand(f"h{i}", "history", 0.5, module=f"h{i}", files=[f"h{i}.py"])
        for i in range(10)
    ]
    chosen = select(pool, total=10, min_history=4, max_net_new=3)
    assert sum(1 for c in chosen if c.source == "net_new") <= 3


def test_module_diversity_enforced():
    """Ensure at least K distinct modules selected."""
    pool = [
        _cand("h1", "history", 0.9, module="A", files=["a1.py"]),
        _cand("h2", "history", 0.89, module="A", files=["a2.py"]),
        _cand("h3", "history", 0.88, module="A", files=["a3.py"]),
        _cand("h4", "history", 0.87, module="A", files=["a4.py"]),
        _cand("h5", "history", 0.86, module="B", files=["b1.py"]),
        _cand("h6", "history", 0.85, module="C", files=["c1.py"]),
        _cand("h7", "history", 0.84, module="D", files=["d1.py"]),
        _cand("h8", "history", 0.83, module="E", files=["e1.py"]),
    ]
    chosen = select(
        pool, total=6, min_history=4, min_distinct_modules=4,
    )
    modules = {c.module for c in chosen}
    assert len(modules) >= 4


def test_dedup_by_files_touched():
    pool = [
        _cand("h1", "history", 0.9, module="A", files=["a.py", "b.py"]),
        _cand("h2", "history", 0.85, module="A", files=["a.py", "b.py"]),  # dup
        _cand("h3", "history", 0.8, module="B", files=["c.py"]),
    ]
    chosen = select(
        pool, total=3, min_history=0, dedup_similarity=0.9,
    )
    assert len(chosen) == 2


def test_dedup_similarity_threshold_below_dedupe():
    pool = [
        _cand("a", "history", 0.9, files=["x.py", "y.py"]),
        _cand("b", "history", 0.85, files=["x.py", "z.py"]),  # jaccard 0.33
    ]
    chosen = select(
        pool, total=2, min_history=0, dedup_similarity=0.5,
    )
    # Not deduped because jaccard 0.33 < 0.5
    assert len(chosen) == 2


def test_higher_score_preferred_within_caps():
    pool = [
        _cand("hi", "excision", 0.9, module="A", files=["a.py"]),
        _cand("lo", "excision", 0.4, module="B", files=["b.py"]),
    ]
    chosen = select(pool, total=1, min_history=0)
    assert chosen[0].id == "hi"


def test_empty_pool_returns_empty():
    assert select([], total=10) == []


def test_pool_smaller_than_total_returns_all_deduped():
    pool = [
        _cand("h1", "history", 0.9, module="A", files=["a.py"]),
        _cand("h2", "history", 0.8, module="B", files=["b.py"]),
    ]
    chosen = select(pool, total=10, min_history=0)
    assert len(chosen) == 2


def test_history_ordering_preserved_by_score():
    pool = [
        _cand("h_low", "history", 0.4, module="A", files=["a.py"]),
        _cand("h_high", "history", 0.9, module="B", files=["b.py"]),
        _cand("h_med", "history", 0.6, module="C", files=["c.py"]),
    ]
    chosen = select(pool, total=2, min_history=2)
    ids = [c.id for c in chosen]
    assert ids == ["h_high", "h_med"]
