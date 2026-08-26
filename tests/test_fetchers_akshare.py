# coding: utf-8
import pandas as pd
import pytest

from data.fetchers.akshare import AksharesSource
from data.fetchers.base import Source


class _FakeAK:
    """假 akshare 门面:按方法名返回预置 DataFrame,记录调用。"""
    def __init__(self, tables):
        self.tables, self.calls = tables, []

    def __getattr__(self, name):
        def _call(**kwargs):
            self.calls.append((name, kwargs))
            return self.tables[name]
        return _call


class _FlakyAK:
    """前 fail_times 次抛连接错误,之后返回数据(模拟 akshare 端点瞬断)。"""
    def __init__(self, method, df, fail_times):
        self.method, self.df, self.fail_times, self.calls = method, df, fail_times, 0

    def __getattr__(self, name):
        def _call(**kwargs):
            self.calls += 1
            if self.calls <= self.fail_times:
                raise ConnectionError("Remote end closed connection without response")
            return self.df
        return _call


CFG = {"data": {"symbols": {"index": ["000300.SH"], "etf": ["511010.SH"], "stock_patch": ["600000.SH"]},
                "backfill_start": "2010-01-01"}}


def test_stock_basic_adds_exchange_suffix_to_bare_codes():
    raw = pd.DataFrame({"code": ["600000", "000001", "300750", "830799", "688981"],
                        "name": ["浦发银行", "平安银行", "宁德时代", "艾融软件", "中芯国际"]})
    src = AksharesSource(CFG, ak=_FakeAK({"stock_info_a_code_name": raw}))
    df = src.fetch("stock_basic", "all")
    assert df["symbol"].tolist() == ["600000.SH", "000001.SZ", "300750.SZ", "830799.BJ", "688981.SH"]


def test_is_source_and_supports_subset():
    src = AksharesSource(CFG, ak=_FakeAK({}))
    assert isinstance(src, Source) and src.name == "akshare"
    # 备源覆盖行情类表(修补用),不覆盖 adj_factor/namechange/index_weight(基准/口径不可混用)
    assert src.supports("stock_daily") and src.supports("index_daily") and src.supports("fund_daily")
    assert src.supports("trade_cal") and src.supports("stock_basic")
    assert not src.supports("adj_factor")
    assert not src.supports("namechange")
    assert not src.supports("index_weight")


def test_stock_daily_maps_to_schema_and_units():
    raw = pd.DataFrame({"日期": ["2026-01-05"], "开盘": [10.0], "最高": [11.0], "最低": [9.0],
                        "收盘": [10.5], "成交量": [1234.0], "成交额": [56789.0]})
    src = AksharesSource(CFG, ak=_FakeAK({"stock_zh_a_hist": raw}))
    df = src.fetch("stock_daily", "600000.SH")
    row = df.iloc[0]
    assert row["symbol"] == "600000.SH" and row["date"] == "20260105"
    assert row["volume"] == 1234.0 * 100                 # akshare 成交量=手→股
    assert row["amount"] == 56789.0                      # akshare 成交额已是元
    assert {"open", "high", "low", "close"} <= set(df.columns)


def test_fetch_retries_transient_connection_errors(monkeypatch):
    monkeypatch.setattr("data.fetchers.akshare.time.sleep", lambda s: None)
    raw = pd.DataFrame({"日期": ["2026-01-05"], "开盘": [10.0], "最高": [11.0], "最低": [9.0],
                        "收盘": [10.5], "成交量": [12.0], "成交额": [34.0]})
    flaky = _FlakyAK("stock_zh_a_hist", raw, fail_times=2)
    src = AksharesSource(CFG, ak=flaky, max_retries=4)
    df = src.fetch("stock_daily", "600000.SH")
    assert len(df) == 1 and flaky.calls == 3       # 前2次断连,第3次成功


def test_fetch_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("data.fetchers.akshare.time.sleep", lambda s: None)
    flaky = _FlakyAK("stock_zh_a_hist", pd.DataFrame(), fail_times=99)
    src = AksharesSource(CFG, ak=flaky, max_retries=3)
    with pytest.raises(ConnectionError):
        src.fetch("stock_daily", "600000.SH")
    assert flaky.calls == 3


def test_plans_by_symbol_from_config():
    # 备源按标的分片(其历史接口是"按标的",不是"按交易日");stock_daily 只修补 config 指定的补丁清单
    src = AksharesSource(CFG, ak=_FakeAK({}))
    assert src.plan("stock_daily", "2026-01-01", "2026-12-31") == ["600000.SH"]
    assert src.plan("index_daily", "2026-01-01", "2026-12-31") == ["000300.SH"]
    assert src.plan("fund_daily", "2026-01-01", "2026-12-31") == ["511010.SH"]
    assert src.plan("stock_basic", "2026-01-01", "2026-12-31") == ["all"]
    assert src.plan("trade_cal", "2010-01-01", "2026-12-31") == ["2010-01-01_2026-12-31"]
