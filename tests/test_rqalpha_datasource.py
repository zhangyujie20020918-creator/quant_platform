# coding: utf-8
"""StoreDataSource:不读任何 bundle 文件,把七个 store 组合成 RQAlpha 完整数据源。
重点核对复权口径:bar 是原始价;history_bars 前复权 = 原始价 × f_t / f_dt;后复权 = 原始价 × f_t(= 自研 hfq)。"""
import datetime as dt

import pytest
from rqalpha.const import INSTRUMENT_TYPE, TRADING_CALENDAR_TYPE

from backtest.rqalpha_adapter.data_source import StoreDataSource
from tests.rq_seed import F_AFTER, F_BEFORE, TRADING_DAYS, seed


@pytest.fixture(scope="module")
def ds(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("rq_ds"))
    cfg = seed(root)
    return StoreDataSource(cfg, root=root)


def _ins(ds, obid):
    return next(iter(ds.get_instruments(id_or_syms=[obid])))


def test_instruments_registered_including_delisted_and_index(ds):
    cs = list(ds.get_instruments(types=[INSTRUMENT_TYPE.CS]))
    assert len(cs) == 8 and any(i.order_book_id == "000003.XSHE" for i in cs)
    assert [i.order_book_id for i in ds.get_instruments(types=[INSTRUMENT_TYPE.INDX])] == ["000001.XSHG", "000300.XSHG"]
    assert list(ds.get_instruments(types=[INSTRUMENT_TYPE.ETF])) == []      # 未注册的类型不报错


def test_trading_calendar_and_data_range(ds):
    assert ds.get_trading_calendars()[TRADING_CALENDAR_TYPE.CN_STOCK].equals(TRADING_DAYS)
    assert ds.available_data_range("1d") == (dt.date(2014, 6, 3), dt.date(2014, 6, 20))


def test_get_bar_is_raw_price_and_missing_day_is_none(ds):
    ins = _ins(ds, "000001.XSHE")
    assert ds.get_bar(ins, dt.date(2014, 6, 12), "1d")["close"] == 9.71
    assert ds.get_bar(ins, dt.date(2014, 6, 16), "1d") is None


def test_history_bars_pre_adjust_rebases_on_query_date(ds):
    ins = _ins(ds, "000001.XSHE")
    at = dt.datetime(2014, 6, 12)
    closes = ds.history_bars(ins, 2, "1d", "close", at, adjust_type="pre", adjust_orig=at)
    assert closes[0] == pytest.approx(11.78 * F_BEFORE / F_AFTER, abs=1e-9)   # ≈ 9.68 = 除权日昨收
    assert closes[1] == 9.71


def test_history_bars_post_adjust_equals_raw_times_factor(ds):
    ins = _ins(ds, "000001.XSHE")
    at = dt.datetime(2014, 6, 12)
    closes = ds.history_bars(ins, 2, "1d", "close", at, adjust_type="post")
    assert closes.tolist() == pytest.approx([11.78 * F_BEFORE, 9.71 * F_AFTER])


def test_history_bars_none_adjust_is_raw(ds):
    ins = _ins(ds, "000001.XSHE")
    at = dt.datetime(2014, 6, 12)
    assert ds.history_bars(ins, 2, "1d", "close", at, adjust_type="none").tolist() == [11.78, 9.71]


def test_ex_cum_factor_keeps_first_value_before_first_record(ds):
    # BaseDataSource 会按上市日过滤并强插 1.0;我们的因子基准不是 1,首值必须保留(否则 1991 上市股全错)
    f = ds.get_ex_cum_factor(_ins(ds, "000001.XSHE"))
    assert f["start_date"][0] == 0 and f["ex_cum_factor"][0] == F_BEFORE


def test_split_from_factor_change_and_no_separate_dividend(ds):
    ins = _ins(ds, "000001.XSHE")
    sp = ds.get_split(ins)
    assert sp["ex_date"][0] == 20140612000000 and sp["split_factor"][0] == pytest.approx(F_AFTER / F_BEFORE)
    assert ds.get_dividend(ins) is None                                   # 分红已含在因子里,不重复计


def test_suspended_and_st_flags(ds):
    assert ds.is_suspended("000001.XSHE", [dt.date(2014, 6, 16), dt.date(2014, 6, 17)]) == [True, False]
    assert ds.is_st_stock("000005.XSHE", [dt.date(2014, 6, 9), dt.date(2014, 6, 10)]) == [False, True]
    assert ds.is_st_stock("600000.XSHG", [dt.date(2014, 6, 10)]) == [False]     # 无记录 → 默认非 ST


def test_yield_curve_is_config_constant(ds):
    yc = ds.get_yield_curve(dt.date(2014, 6, 3), dt.date(2014, 6, 3), tenor=["1M"])
    assert yc.iloc[0]["1M"] == 0.02


def test_no_share_transformation(ds):
    assert ds.get_share_transformation("000001.XSHE") is None


def test_preload_accepts_platform_symbols(ds):
    ds.preload(["000001.SZ", "600000.SH"])
    assert ds.get_bar(_ins(ds, "600000.XSHG"), dt.date(2014, 6, 3), "1d")["close"] == 10.0


def test_risk_free_rate_zero_is_not_treated_as_missing(tmp_path):
    # RQAlpha DataProxy.get_risk_free_rate 把利率 0 当缺失(if rate ...)→ NaN → 报表 sharpe/alpha 全 NaN
    from rqalpha.data.data_proxy import DataProxy
    root = str(tmp_path)
    cfg = seed(root)
    cfg["backtest"]["risk_free_rate"] = 0.0
    proxy = DataProxy(StoreDataSource(cfg, root=root), None)
    rate = proxy.get_risk_free_rate(dt.date(2014, 6, 3), dt.date(2014, 6, 20))
    assert rate == pytest.approx(0.0, abs=1e-9) and not (rate != rate)      # 不是 NaN
