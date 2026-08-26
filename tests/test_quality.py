# coding: utf-8
import os

import pandas as pd

from data import quality, store


def _seed(root, trading_days, stocks, daily_rows, weights=None):
    for _, r in stocks.iterrows():
        pass
    store.write_part("stock_basic", "tushare", "all", stocks.assign(source="tushare"), root=root)
    store.consolidate("stock_basic", root=root)
    cal = pd.DataFrame({"date": trading_days, "exchange": "SSE", "is_open": 1, "source": "tushare"})
    store.write_part("trade_cal", "tushare", "all", cal, root=root)
    store.consolidate("trade_cal", root=root)
    store.write_part("stock_daily", "tushare", "all", daily_rows.assign(source="tushare"), root=root)
    store.consolidate("stock_daily", root=root)
    if weights is not None:
        store.write_part("index_weight", "tushare", "all", weights.assign(source="tushare"), root=root)
        store.consolidate("index_weight", root=root)


def _daily(dates, symbol, close=10.0, **over):
    df = pd.DataFrame({"date": dates, "symbol": symbol, "open": close, "high": close, "low": close,
                       "close": close, "pre_close": close, "volume": 100.0, "amount": 1000.0})
    for k, v in over.items():
        df[k] = v
    return df


def _basic(symbols, statuses, delist=None):
    return pd.DataFrame({"symbol": symbols, "name": ["x"] * len(symbols), "exchange": "SSE",
                         "market": "主板", "list_status": statuses,
                         "list_date": "20050101", "delist_date": delist or [None] * len(symbols)})


CFG = {"calendar": {"exchange": "SSE"},
       "quality": {"min_delisted_count": 1, "max_snapshot_gap_days": 45,
                   "max_dirty_ratio": 0.001, "min_daily_coverage": 0.95}}


def test_delisting_check_passes_when_delisted_present(tmp_path):
    root = str(tmp_path)
    stocks = _basic(["600000.SH", "600001.SH"], ["L", "D"], delist=[None, "20100114"])
    days = ["20260105", "20260106"]
    daily = pd.concat([_daily(days, "600000.SH"), _daily(["20091231"], "600001.SH")])
    _seed(root, days + ["20091231"], stocks, daily)
    r = quality.check_delisting(CFG, root=root)
    assert r["passed"] and r["delisted_count"] == 1
    assert r["delisted_with_history"] == 1        # 退市股在 stock_daily 有退市前行情


def test_delisting_check_fails_when_no_delisted(tmp_path):
    root = str(tmp_path)
    stocks = _basic(["600000.SH"], ["L"])
    _seed(root, ["20260105"], stocks, _daily(["20260105"], "600000.SH"))
    r = quality.check_delisting(CFG, root=root)
    assert not r["passed"] and r["delisted_count"] == 0


def test_pit_check_flags_daily_after_calendar_and_snapshot_gap(tmp_path):
    root = str(tmp_path)
    stocks = _basic(["600000.SH"], ["L"])
    days = ["20260105", "20260106"]
    # 一行日线晚于日历最新开市日 → PIT 违规
    daily = pd.concat([_daily(days, "600000.SH"), _daily(["20260109"], "600000.SH")])
    weights = pd.DataFrame({"date": ["20250131", "20250630"], "index_symbol": "000300.SH",
                            "symbol": "600000.SH", "weight": 1.0})   # 间隔>45天
    _seed(root, days, stocks, daily, weights=weights)
    r = quality.check_pit(CFG, root=root)
    assert not r["passed"]
    assert r["daily_after_calendar"] == 1
    assert r["max_snapshot_gap"] > 45


def test_pit_check_passes_clean(tmp_path):
    root = str(tmp_path)
    stocks = _basic(["600000.SH"], ["L"])
    days = ["20260105", "20260106"]
    weights = pd.DataFrame({"date": ["20250131", "20250228"], "index_symbol": "000300.SH",
                            "symbol": "600000.SH", "weight": 1.0})
    _seed(root, days, stocks, _daily(days, "600000.SH"), weights=weights)
    r = quality.check_pit(CFG, root=root)
    assert r["passed"] and r["daily_after_calendar"] == 0


def test_dirty_check_counts_bad_rows(tmp_path):
    root = str(tmp_path)
    stocks = _basic(["600000.SH"], ["L"])
    days = ["20260105", "20260106", "20260107", "20260108"]
    daily = _daily(days, "600000.SH")
    daily.loc[daily["date"] == "20260106", "close"] = -1.0        # 价格≤0
    daily.loc[daily["date"] == "20260107", "high"] = 1.0
    daily.loc[daily["date"] == "20260107", "low"] = 99.0          # high<low
    _seed(root, days, stocks, daily)
    r = quality.check_dirty(CFG, root=root)
    assert r["dirty_rows"] == 2 and not r["passed"]               # 2/4 > 0.001
    assert set(r["reasons"]) >= {"price<=0", "high<low"}


def test_coverage_check_reports_low_days(tmp_path):
    root = str(tmp_path)
    stocks = _basic(["600000.SH", "600001.SH"], ["L", "L"])
    days = ["20260105", "20260106"]
    # 第二天只有1/2只有行情 → 覆盖率 0.5 < 0.95
    daily = pd.concat([_daily(days, "600000.SH"), _daily(["20260105"], "600001.SH")])
    _seed(root, days, stocks, daily)
    r = quality.check_coverage(CFG, root=root)
    assert not r["passed"]
    assert r["low_coverage_days"] == 1 and r["min_coverage"] == 0.5


def test_run_all_writes_report(tmp_path):
    root = str(tmp_path)
    stocks = _basic(["600000.SH", "600001.SH"], ["L", "D"], delist=[None, "20100114"])
    days = ["20260105", "20260106"]
    daily = pd.concat([_daily(days, "600000.SH"), _daily(days, "600001.SH")])
    _seed(root, days, stocks, daily)
    summary = quality.run_all(CFG, root=root, date="2026-08-26")
    assert set(summary["checks"]) == {"delisting", "pit", "dirty", "coverage"}
    report = os.path.join(root, "reports", "2026-08-26_数据体检", "quality_report.md")
    assert os.path.exists(report)
    text = open(report, encoding="utf-8").read()
    assert "退市样本" in text and "覆盖" in text
