# coding: utf-8
"""指数成分 PIT universe 测试(instruments 层,独立于 strategy——断因子⇄策略环的根治)。"""
import pandas as pd

from data import store
from instruments.universe import index_constituents, IndexUniverse


def _seed_weights(root, rows):
    store.write_part("index_weight", "tushare", "all", rows.assign(source="tushare"), root=root)
    store.consolidate("index_weight", root=root)


def _weights(snapshots):
    """snapshots: {date: [symbols]} → index_weight 行(等权占位)。"""
    recs = []
    for d, syms in snapshots.items():
        for s in syms:
            recs.append({"date": d, "index_symbol": "000300.SH", "symbol": s, "weight": 100.0 / len(syms)})
    return pd.DataFrame(recs)


def test_pit_uses_most_recent_snapshot_on_or_before_date(tmp_path):
    root = str(tmp_path)
    _seed_weights(root, _weights({"2026-01-31": ["600000.SH", "600001.SH"],
                                  "2026-06-30": ["600000.SH", "600002.SH"]}))
    # 3月:用1月快照;7月:用6月快照;1月前:空
    assert index_constituents("000300.SH", "2026-03-15", root=root) == ["600000.SH", "600001.SH"]
    assert index_constituents("000300.SH", "2026-07-15", root=root) == ["600000.SH", "600002.SH"]
    assert index_constituents("000300.SH", "2026-01-30", root=root) == []


def test_uses_exact_snapshot_date(tmp_path):
    root = str(tmp_path)
    _seed_weights(root, _weights({"2026-01-31": ["600000.SH"]}))
    assert index_constituents("000300.SH", "2026-01-31", root=root) == ["600000.SH"]


def test_index_universe_caches_and_serves_multiple_dates(tmp_path):
    root = str(tmp_path)
    _seed_weights(root, _weights({"2026-01-31": ["600000.SH", "600001.SH"],
                                  "2026-06-30": ["600002.SH"]}))
    uni = IndexUniverse("000300.SH", root=root)
    assert uni.constituents("2026-02-01") == ["600000.SH", "600001.SH"]
    assert uni.constituents("2026-07-01") == ["600002.SH"]
    assert sorted(uni.all_symbols()) == ["600000.SH", "600001.SH", "600002.SH"]   # 历史出现过的全集


def test_empty_when_index_absent(tmp_path):
    root = str(tmp_path)
    _seed_weights(root, _weights({"2026-01-31": ["600000.SH"]}))
    assert index_constituents("999999.SH", "2026-03-15", root=root) == []
