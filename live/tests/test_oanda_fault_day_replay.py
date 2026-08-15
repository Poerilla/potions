"""Fault-day bar replay: real OANDA demo bars + frozen books → containment."""

from __future__ import annotations

from potions.live.demo.oanda_fault_replay import FIXTURE_ROOT, iter_fault_books, run_all


def test_fixture_root_exists():
    assert FIXTURE_ROOT.exists()


def test_aug13_stop_only_has_bar_slices():
    books = {
        book.name: book
        for case, book in iter_fault_books("2026-08-13_stop_only_v2b")
    }
    assert "nas100" in books and "spx500" in books
    for name in ("nas100", "spx500"):
        bars_dir = books[name] / "bars"
        assert bars_dir.exists(), name
        csvs = list(bars_dir.glob("*.csv"))
        assert csvs, name
        # Day slice should be non-trivial (prior evening pad + Aug 13).
        lines = sum(1 for _ in csvs[0].open(encoding="utf-8")) - 1
        assert lines > 500, (name, lines)


def test_aug14_orphan_has_bar_slices():
    books = list(iter_fault_books("2026-08-14_orphan_stop_flat_v2b"))
    assert len(books) == 2
    for _, book in books:
        assert list((book / "bars").glob("*.csv"))


def test_fault_day_replay_all_pass_live_mode():
    results = run_all(mode="live", also_plugin_replay=False)
    assert results, "expected curated fault books"
    failed = [r for r in results if not r.ok]
    assert not failed, [(r.case, r.book, r.containment_classification, r.supervisor_mode) for r in failed]


def test_fault_day_replay_with_plugin_smoke_on_bar_cases():
    results = run_all(case="2026-08-13_stop_only_v2b", mode="live", also_plugin_replay=True)
    assert results
    assert all(r.ok for r in results)
    for r in results:
        assert r.bar_count > 0
        assert r.plugin_replay is not None
        assert r.plugin_replay.get("status") == "ok"
        assert int(r.plugin_replay.get("bars_played") or 0) > 0
