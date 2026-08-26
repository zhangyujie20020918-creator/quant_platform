# coding: utf-8
"""前/后复权价格面板读取测试(接引擎与策略的真实数据入口)。"""
import pandas as pd

from backtest.prices import adjusted_panels
from data import store


def _seed(root, rows_daily, rows_adj):
    store.write_part("stock_daily", "tushare", "all", rows_daily.assign(source="tushare"), root=root)
    store.consolidate("stock_daily", root=root)
    store.write_part("adj_factor", "tushare", "all", rows_adj.assign(source="tushare"), root=root)
    store.consolidate("adj_factor", root=root)


def _daily(dates, symbol, close, open_=None):
    n = len(dates)
    o = open_ if open_ is not None else close
    return pd.DataFrame({"date": dates, "symbol": symbol,
                         "open": o, "high": close, "low": close, "close": close,
                         "pre_close": close, "volume": 100.0, "amount": 1000.0})


def test_hfq_multiplies_close_by_adj_factor(tmp_path):
    root = str(tmp_path)
    dates = ["2026-01-05", "2026-01-06", "2026-01-07"]
    daily = _daily(dates, "600000.SH", close=[10.0, 11.0, 12.0], open_=[9.9, 10.9, 11.9])
    adj = pd.DataFrame({"date": dates, "symbol": "600000.SH", "adj_factor": [2.0, 2.0, 3.0]})
    _seed(root, daily, adj)
    opens, closes = adjusted_panels(["600000.SH"], "2026-01-05", "2026-01-07", root=root, method="hfq")
    # 后复权 = 原始价 × adj_factor
    assert closes["600000.SH"].tolist() == [20.0, 22.0, 36.0]
    assert opens["600000.SH"].tolist() == [19.8, 21.8, 35.7]
    assert list(closes.index) == list(pd.to_datetime(dates))


def test_qfq_rebases_on_latest_factor(tmp_path):
    root = str(tmp_path)
    dates = ["2026-01-05", "2026-01-06"]
    daily = _daily(dates, "600000.SH", close=[10.0, 11.0])
    adj = pd.DataFrame({"date": dates, "symbol": "600000.SH", "adj_factor": [1.0, 2.0]})
    _seed(root, daily, adj)
    _, closes = adjusted_panels(["600000.SH"], "2026-01-05", "2026-01-06", root=root, method="qfq")
    # 前复权 = 原始 × adj / 最新adj:10*1/2=5, 11*2/2=11
    assert closes["600000.SH"].tolist() == [5.0, 11.0]


def test_multiple_symbols_align_on_dates(tmp_path):
    root = str(tmp_path)
    a = _daily(["2026-01-05", "2026-01-06"], "600000.SH", close=[10.0, 11.0])
    b = _daily(["2026-01-06"], "000001.SZ", close=[20.0])
    daily = pd.concat([a, b])
    adj = pd.DataFrame({"date": ["2026-01-05", "2026-01-06", "2026-01-06"],
                        "symbol": ["600000.SH", "600000.SH", "000001.SZ"], "adj_factor": [1.0, 1.0, 1.0]})
    _seed(root, daily, adj)
    _, closes = adjusted_panels(["600000.SH", "000001.SZ"], "2026-01-05", "2026-01-06", root=root)
    assert list(closes.columns) == ["600000.SH", "000001.SZ"]
    assert pd.isna(closes.loc["2026-01-05", "000001.SZ"])   # B当天无数据→NaN
    assert closes.loc["2026-01-06", "000001.SZ"] == 20.0


def test_missing_adj_factor_falls_back_to_raw(tmp_path):
    root = str(tmp_path)
    dates = ["2026-01-05"]
    daily = _daily(dates, "600000.SH", close=[10.0])
    adj = pd.DataFrame({"date": ["2026-01-05"], "symbol": ["999999.SH"], "adj_factor": [2.0]})  # 不匹配
    _seed(root, daily, adj)
    _, closes = adjusted_panels(["600000.SH"], "2026-01-05", "2026-01-05", root=root, method="hfq")
    assert closes["600000.SH"].tolist() == [10.0]     # 无复权因子→用原始价(复权因子=1)
