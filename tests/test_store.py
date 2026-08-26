# coding: utf-8
import os

import pandas as pd
import pytest

from data import store
from data.schema import SchemaError


def _rows(dates, symbol, close, source):
    return pd.DataFrame({
        "date": dates, "symbol": symbol, "open": close, "high": close, "low": close,
        "close": close, "pre_close": close, "volume": 100.0, "amount": 1000.0, "source": source})


def test_write_part_then_has_part_and_list(tmp_path):
    root = str(tmp_path)
    assert not store.has_part("stock_daily", "tushare", "20260105", root=root)
    p = store.write_part("stock_daily", "tushare", "20260105",
                         _rows(["20260105"], "600000.SH", 10.0, "tushare"), root=root)
    assert os.path.exists(p) and p.endswith(os.path.join("_parts", "tushare__20260105.parquet"))
    assert store.has_part("stock_daily", "tushare", "20260105", root=root)
    parts = store.list_parts("stock_daily", root=root)
    assert [(s, c) for s, c, _ in parts] == [("tushare", "20260105")]


def test_empty_part_is_recorded_so_resume_skips_it(tmp_path):
    root = str(tmp_path)
    empty = _rows([], "600000.SH", 1.0, "tushare").iloc[0:0]
    store.write_part("stock_daily", "tushare", "20260103", empty, root=root)   # 非交易日:空分片
    assert store.has_part("stock_daily", "tushare", "20260103", root=root)
    df = store.consolidate("stock_daily", root=root)
    assert df.empty and "close" in df.columns


def test_write_part_rejects_bad_schema_without_leaving_file(tmp_path):
    root = str(tmp_path)
    bad = _rows(["20260105"], "600000.SH", 10.0, "tushare").drop(columns=["close"])
    with pytest.raises(SchemaError):
        store.write_part("stock_daily", "tushare", "20260105", bad, root=root)
    assert not store.has_part("stock_daily", "tushare", "20260105", root=root)


def test_consolidate_dedupes_by_key_with_source_priority(tmp_path):
    root = str(tmp_path)
    store.write_part("stock_daily", "akshare", "600000.SH",
                     _rows(["20260105", "20260106"], "600000.SH", 99.0, "akshare"), root=root)
    store.write_part("stock_daily", "tushare", "20260106",
                     _rows(["20260106"], "600000.SH", 10.0, "tushare"), root=root)
    df = store.consolidate("stock_daily", source_priority=["tushare", "akshare"], root=root)
    assert len(df) == 2
    d6 = df[df["date"] == pd.Timestamp("2026-01-06")].iloc[0]
    assert d6["close"] == 10.0 and d6["source"] == "tushare"          # 主源赢
    d5 = df[df["date"] == pd.Timestamp("2026-01-05")].iloc[0]
    assert d5["close"] == 99.0 and d5["source"] == "akshare"          # 备源补缺
    assert df["date"].is_monotonic_increasing
    assert os.path.exists(os.path.join(root, "cache", "stock_daily", "stock_daily.parquet"))


def test_read_table_filters_by_date_symbols_columns(tmp_path):
    root = str(tmp_path)
    store.write_part("stock_daily", "tushare", "a",
                     _rows(["20260105", "20260106", "20260107"], "600000.SH", 1.0, "tushare"), root=root)
    store.write_part("stock_daily", "tushare", "b",
                     _rows(["20260105", "20260106"], "000001.SZ", 2.0, "tushare"), root=root)
    store.consolidate("stock_daily", root=root)
    df = store.read_table("stock_daily", start="2026-01-06", end="2026-01-07", root=root)
    assert len(df) == 3
    df = store.read_table("stock_daily", symbols=["000001.SZ"], columns=["date", "close"], root=root)
    assert list(df.columns) == ["date", "close"] and len(df) == 2 and (df["close"] == 2.0).all()


def test_read_table_returns_empty_frame_with_spec_columns_when_absent(tmp_path):
    df = store.read_table("stock_daily", root=str(tmp_path))
    assert df.empty and list(df.columns)[:2] == ["date", "symbol"]


def test_table_status(tmp_path):
    root = str(tmp_path)
    assert store.table_status("stock_daily", root=root)["exists"] is False
    store.write_part("stock_daily", "tushare", "x",
                     _rows(["20260105", "20260106"], "600000.SH", 1.0, "tushare"), root=root)
    store.write_part("stock_daily", "akshare", "y",
                     _rows(["20260107"], "600000.SH", 1.0, "akshare"), root=root)
    store.consolidate("stock_daily", root=root)
    st = store.table_status("stock_daily", root=root)
    assert st["exists"] and st["rows"] == 3 and st["parts"] == 2
    assert st["date_min"] == "2026-01-05" and st["date_max"] == "2026-01-07"
    assert st["sources"] == {"tushare": 2, "akshare": 1}


def test_static_table_status_has_no_dates(tmp_path):
    root = str(tmp_path)
    basic = pd.DataFrame({"symbol": ["600000.SH"], "name": ["浦发银行"], "exchange": ["SSE"],
                          "market": ["主板"], "list_status": ["L"], "list_date": ["19991110"],
                          "delist_date": [None], "source": ["tushare"]})
    store.write_part("stock_basic", "tushare", "L", basic, root=root)
    store.consolidate("stock_basic", root=root)
    st = store.table_status("stock_basic", root=root)
    assert st["rows"] == 1 and st["date_min"] is None
