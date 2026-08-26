# coding: utf-8
import os

import pandas as pd
import pytest

from data import fetch, store
from data.fetchers.base import Source, SourceUnavailable


class FakeSource(Source):
    """可编程假来源:records 记录 fetch 调用;raise_on 指定某分片抛异常。"""
    def __init__(self, name, tables, chunks_by_table, rows_by_chunk=None, raise_on=None):
        self.name = name
        self._tables = set(tables)
        self._chunks = chunks_by_table
        self._rows = rows_by_chunk or {}
        self._raise_on = raise_on or {}
        self.records = []

    def supports(self, table):
        return table in self._tables

    def plan(self, table, start, end):
        return list(self._chunks[table])

    def fetch(self, table, chunk):
        self.records.append((table, chunk))
        if (table, chunk) in self._raise_on:
            raise self._raise_on[(table, chunk)]
        close = self._rows.get((table, chunk), 1.0)
        return pd.DataFrame({"date": ["20260105"], "symbol": ["600000.SH"], "open": [close], "high": [close],
                             "low": [close], "close": [close], "pre_close": [close], "volume": [1.0], "amount": [1.0]})


def _daily_source(name, close=1.0, chunks=("20260105", "20260106"), raise_on=None):
    return FakeSource(name, ["stock_daily"], {"stock_daily": chunks},
                      rows_by_chunk={("stock_daily", c): close for c in chunks}, raise_on=raise_on)


def test_fetch_table_writes_parts_and_consolidates(tmp_path):
    root = str(tmp_path)
    src = _daily_source("tushare")
    res = fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-06", sources=[src], root=root, cfg={})
    assert res["fetched"] == 2 and res["skipped"] == 0 and res["failed"] == 0
    assert store.table_status("stock_daily", root=root)["rows"] == 1     # 两分片同键,合并去重
    assert {c for _, c in src.records} == {"20260105", "20260106"}


def test_resume_skips_existing_closed_parts(tmp_path):
    root = str(tmp_path)
    src = _daily_source("tushare")
    fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-06", sources=[src], root=root, cfg={})
    src2 = _daily_source("tushare")
    res = fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-06", sources=[src2], root=root, cfg={})
    assert res["skipped"] == 2 and res["fetched"] == 0 and src2.records == []


def test_force_refetches_existing_parts(tmp_path):
    root = str(tmp_path)
    fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-06", sources=[_daily_source("tushare")], root=root, cfg={})
    src2 = _daily_source("tushare")
    res = fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-06", sources=[src2], root=root, cfg={}, force=True)
    assert res["fetched"] == 2 and len(src2.records) == 2


def test_single_chunk_failure_is_recorded_not_fatal(tmp_path):
    root = str(tmp_path)
    src = _daily_source("tushare", raise_on={("stock_daily", "20260106"): ValueError("bad row")})
    res = fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-06", sources=[src], root=root, cfg={})
    assert res["fetched"] == 1 and res["failed"] == 1
    fails = pd.read_csv(os.path.join(root, "cache", "fetch_failures.csv"), dtype=str)
    assert len(fails) == 1 and fails.iloc[0]["chunk"] == "20260106" and "bad row" in fails.iloc[0]["error"]


def test_source_unavailable_switches_to_backup(tmp_path):
    root = str(tmp_path)
    primary = _daily_source("tushare", raise_on={("stock_daily", "20260105"): SourceUnavailable("token dead")})
    backup = _daily_source("akshare", close=9.0)
    res = fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-06", sources=[primary, backup], root=root, cfg={})
    assert res["source_used"] == "akshare" and res["fetched"] == 2
    # 主源在第一个分片就判定不可用,不再继续它后续分片
    assert primary.records == [("stock_daily", "20260105")]
    df = store.read_table("stock_daily", root=root)
    assert (df["source"] == "akshare").all()


def test_transient_failures_do_not_switch_to_incomplete_backup(tmp_path):
    """核心回归:主源瞬断(非SourceUnavailable)绝不能切到覆盖不了这些分片的备源、
    然后把缺数据的表当'完成'。必须留在主源、如实报 failed,不静默切换。
    (这正是全市场回补只拉到2014就'完成'那个数据完整性bug的复现。)"""
    root = str(tmp_path)
    chunks = ("20260105", "20260106", "20260107")
    raise_all = {("stock_daily", c): ConnectionError("net drop") for c in chunks}
    primary = _daily_source("tushare", chunks=chunks, raise_on=raise_all)
    backup = FakeSource("akshare", ["stock_daily"], {"stock_daily": []})   # 备源对该表空plan(现实:stock_patch=[])
    res = fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-07", sources=[primary, backup], root=root,
                            cfg={}, chunk_retries=1)
    assert res["source_used"] == "tushare"       # 没切走
    assert res["failed"] == 3 and res["fetched"] == 0
    assert backup.records == []                  # 备源根本没被调用
    assert store.read_table("stock_daily", root=root).empty


def test_fetch_table_retries_failed_chunks_on_same_source(tmp_path):
    """瞬断分片在同一来源内重试;临时故障恢复后应补齐。"""
    root = str(tmp_path)

    class FlakyOnce(FakeSource):
        def __init__(self):
            super().__init__("tushare", ["stock_daily"], {"stock_daily": ["20260105", "20260106"]},
                             rows_by_chunk={("stock_daily", "20260105"): 1.0, ("stock_daily", "20260106"): 2.0})
            self._failed_once = set()

        def fetch(self, table, chunk):
            if chunk == "20260106" and chunk not in self._failed_once:
                self._failed_once.add(chunk)
                self.records.append((table, chunk))
                raise ConnectionError("transient")
            return super().fetch(table, chunk)

    src = FlakyOnce()
    res = fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-06", sources=[src], root=root, cfg={}, chunk_retries=2)
    assert res["fetched"] == 2 and res["failed"] == 0        # 第二遍补齐
    assert store.table_status("stock_daily", root=root)["rows"] == 1   # 两分片同键合并


def test_persistent_failure_recorded_once_after_retries(tmp_path):
    root = str(tmp_path)
    src = _daily_source("tushare", raise_on={("stock_daily", "20260106"): ValueError("bad row")})
    res = fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-06", sources=[src], root=root, cfg={}, chunk_retries=2)
    assert res["fetched"] == 1 and res["failed"] == 1
    fails = pd.read_csv(os.path.join(root, "cache", "fetch_failures.csv"), dtype=str)
    assert len(fails) == 1        # 重试多次,但只在最终放弃时记一条


def test_fetch_tables_retries_table_with_failures_then_reports(tmp_path, caplog):
    """整表若仍有失败分片,fetch_tables 要重试并最终大声报警,绝不静默当完成。"""
    import logging
    root = str(tmp_path)

    class FlakyTable(FakeSource):
        def __init__(self):
            super().__init__("tushare", ["stock_daily"], {"stock_daily": ["20260105", "20260106"]},
                             rows_by_chunk={("stock_daily", c): 1.0 for c in ["20260105", "20260106"]})
            self.calls_for_06 = 0

        def fetch(self, table, chunk):
            if chunk == "20260106":
                self.calls_for_06 += 1
                if self.calls_for_06 <= 3:      # 头几次(含表级重试)都失败
                    self.records.append((table, chunk))
                    raise ConnectionError("net")
            return super().fetch(table, chunk)

    src = FlakyTable()
    with caplog.at_level(logging.WARNING):
        results = fetch.fetch_tables(["stock_daily"], "2026-01-05", "2026-01-06",
                                     cfg={}, root=root, sources_factory=lambda cfg, root: [src],
                                     chunk_retries=0, table_retries=3)
    assert results["stock_daily"]["failed"] == 0     # 表级重试最终补齐
    assert "重试" in caplog.text


def test_no_source_supports_table_raises(tmp_path):
    with pytest.raises(LookupError, match="index_weight"):
        fetch.fetch_table("index_weight", "2026-01-01", "2026-12-31",
                          sources=[_daily_source("tushare")], root=str(tmp_path), cfg={})


def test_open_chunk_always_refetched(tmp_path):
    root = str(tmp_path)

    class OpenSrc(_daily_source("tushare").__class__):
        def is_open_chunk(self, table, chunk):
            return chunk == "20260106"

    src = OpenSrc("tushare", ["stock_daily"], {"stock_daily": ["20260105", "20260106"]},
                  rows_by_chunk={("stock_daily", "20260105"): 1.0, ("stock_daily", "20260106"): 1.0})
    fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-06", sources=[src], root=root, cfg={})
    src2 = OpenSrc("tushare", ["stock_daily"], {"stock_daily": ["20260105", "20260106"]},
                   rows_by_chunk={("stock_daily", "20260105"): 1.0, ("stock_daily", "20260106"): 1.0})
    res = fetch.fetch_table("stock_daily", "2026-01-05", "2026-01-06", sources=[src2], root=root, cfg={})
    assert res["skipped"] == 1 and res["fetched"] == 1        # 封口分片跳过,未封口分片重拉
    assert src2.records == [("stock_daily", "20260106")]
