# coding: utf-8
"""RQAlpha 各 store 适配:每个 store 从我们 store 的对应表供数,格式与 bundle 一致。"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest
from rqalpha.const import INSTRUMENT_TYPE

from backtest.rqalpha_adapter import stores as S
from tests.rq_seed import F_AFTER, F_BEFORE, TRADING_DAYS, seed


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("rq"))
    cfg = seed(root)
    return root, cfg


# ---------- 日历 ----------

def test_calendar_store_serves_trading_days_from_core_calendar(world):
    root, cfg = world
    cal = S.StoreCalendarStore.load(cfg, root)
    assert cal.get_trading_calendar().equals(pd.DatetimeIndex(TRADING_DAYS))


def test_calendar_store_refuses_weekday_approximation(tmp_path):
    with pytest.raises(RuntimeError):
        S.StoreCalendarStore.load({"calendar": {"file": "nope.csv"}}, str(tmp_path))


# ---------- instruments ----------

def test_instrument_table_builds_cs_and_indx_instruments(world):
    root, cfg = world
    table = S.InstrumentTable.load(cfg, root)
    ins = {i.order_book_id: i for i in table.instruments()}
    pa = ins["000001.XSHE"]
    assert pa.type == INSTRUMENT_TYPE.CS and pa.exchange == "XSHE" and pa.symbol == "平安银行"
    assert pa.listed_date == dt.datetime(1991, 4, 3) and pa.de_listed_date == dt.datetime(2999, 12, 31)
    assert pa.board_type == "MainBoard" and pa.status == "Active"
    assert pa.round_lot == 100 and pa.market_tplus == 1
    dead = ins["000003.XSHE"]
    assert dead.status == "Delisted" and dead.de_listed_date == dt.datetime(2002, 6, 14)
    ksh = ins["688001.XSHG"]
    assert ksh.board_type == "KSH" and ksh.min_order_quantity == 200 and ksh.order_step_size == 1
    assert ins["300001.XSHE"].board_type == "GEM"
    assert ins["999999.XSHE"].board_type == "MainBoard"       # market 缺失按主板
    idx = ins["000300.XSHG"]
    assert idx.type == INSTRUMENT_TYPE.INDX and idx.listed_date == dt.datetime(2014, 6, 3)
    assert idx.market_tplus == 0 and idx.round_lot == 1


def test_instrument_table_board_lookup_by_symbol(world):
    root, cfg = world
    table = S.InstrumentTable.load(cfg, root)
    assert table.board("300001.SZ") == "GEM" and table.board("000001.SZ") == "MainBoard"
    assert table.board("000300.SH") is None


# ---------- ST ----------

def test_st_dateset_from_namechange_intervals(world):
    root, cfg = world
    st = S.StoreSTDateSet.load(cfg, root)
    dates = [dt.date(2014, 6, 9), dt.datetime(2014, 6, 10), 20140611, 20140612000000, pd.Timestamp("2014-06-20")]
    assert st.contains("000005.XSHE", dates) == [False, True, True, True, True]
    assert st.contains("000001.XSHE", [dt.date(2014, 6, 9)]) == [False]      # 有改名记录但从未 ST
    assert st.contains("600000.XSHG", [dt.date(2014, 6, 9)]) is None         # 无记录 → None(RQAlpha 约定)


def test_st_flags_vectorized_for_bar_building(world):
    root, cfg = world
    st = S.StoreSTDateSet.load(cfg, root)
    flags = st.flags("000005.SZ", pd.DatetimeIndex(TRADING_DAYS))
    assert flags.tolist() == [False] * 5 + [True] * 9


# ---------- 日线 bar ----------

def test_cs_day_bars_raw_prices_and_bundle_dtype(world):
    root, cfg = world
    bars = S.StoreDayBarStore.for_stocks(cfg, root).get_bars("000001.XSHE")
    assert bars.dtype.names == ("datetime", "open", "close", "high", "low", "volume", "total_turnover",
                                "limit_up", "limit_down")
    assert len(bars) == 13 and bars["datetime"][0] == 20140603000000
    ex = bars[bars["datetime"] == 20140612000000][0]
    assert ex["close"] == 9.71 and ex["open"] == 9.62                         # 原始价,未复权
    assert ex["total_turnover"] == 9.71 * 1_000_000                            # amount(元)
    assert ex["limit_up"] == 10.65 and ex["limit_down"] == 8.71                # 昨收 9.68 × (1±10%),四舍五入


def test_cs_day_bars_st_limit_and_first_day_no_limit(world):
    root, cfg = world
    st_bars = S.StoreDayBarStore.for_stocks(cfg, root).get_bars("000005.XSHE")
    d09 = st_bars[st_bars["datetime"] == 20140609000000][0]
    d10 = st_bars[st_bars["datetime"] == 20140610000000][0]
    assert (d09["limit_up"], d09["limit_down"]) == (3.30, 2.70)                # 未 ST:10%
    assert (d10["limit_up"], d10["limit_down"]) == (3.15, 2.85)                # ST:5%
    new = S.StoreDayBarStore.for_stocks(cfg, root).get_bars("999999.XSHE")
    assert np.isnan(new["limit_up"][0]) and np.isnan(new["limit_down"][0])     # 上市首日无涨跌停
    assert new["limit_up"][1] == 7.92                                          # 次日起 7.2×1.1


def test_cs_day_bars_unknown_symbol_empty_and_date_range(world):
    root, cfg = world
    s = S.StoreDayBarStore.for_stocks(cfg, root)
    assert len(s.get_bars("123456.XSHE")) == 0
    assert s.get_date_range("000001.XSHE") == (20140603000000, 20140620000000)


def test_cs_day_bars_preload_matches_lazy_load(world):
    root, cfg = world
    lazy = S.StoreDayBarStore.for_stocks(cfg, root)
    pre = S.StoreDayBarStore.for_stocks(cfg, root)
    pre.preload(["000001.XSHE", "600000.XSHG"])
    assert np.array_equal(pre.get_bars("000001.XSHE"), lazy.get_bars("000001.XSHE"))
    assert np.array_equal(pre.get_bars("600000.XSHG"), lazy.get_bars("600000.XSHG"))


def test_index_day_bars_seven_fields(world):
    root, cfg = world
    bars = S.StoreDayBarStore.for_indexes(cfg, root).get_bars("000300.XSHG")
    assert bars.dtype.names == ("datetime", "open", "close", "high", "low", "volume", "total_turnover")
    assert len(bars) == 14 and bars["close"][-1] == 2113.0


# ---------- 复权因子:ex_cum_factor(看历史)与合成 split(持仓过除权日) ----------

def test_ex_cum_factor_from_adj_factor_changes(world):
    root, cfg = world
    adj = S.StoreAdjFactorStore(cfg, root)
    f = adj.ex_cum_factors().get_factors("000001.XSHE")
    assert f.dtype.names == ("start_date", "ex_cum_factor")
    assert f["start_date"].tolist() == [0, 20140612000000]
    assert f["ex_cum_factor"].tolist() == [F_BEFORE, F_AFTER]
    const = adj.ex_cum_factors().get_factors("600000.XSHG")
    assert const["start_date"].tolist() == [0] and const["ex_cum_factor"].tolist() == [2.0]
    assert adj.ex_cum_factors().get_factors("123456.XSHE") is None


def test_split_factors_are_adj_factor_ratios_on_change_dates(world):
    root, cfg = world
    adj = S.StoreAdjFactorStore(cfg, root)
    sp = adj.split_factors().get_factors("000001.XSHE")
    assert sp.dtype.names == ("ex_date", "split_factor")
    assert sp["ex_date"].tolist() == [20140612000000]
    assert sp["split_factor"][0] == pytest.approx(F_AFTER / F_BEFORE)
    assert adj.split_factors().get_factors("600000.XSHG") is None            # 因子从未变动 → 无事件


# ---------- 停牌:交易日 ∧ 数据区间内 ∧ 无行 ----------

def test_suspended_dateset_derived_from_missing_rows(world):
    root, cfg = world
    bars = S.StoreDayBarStore.for_stocks(cfg, root)
    cal = S.StoreCalendarStore.load(cfg, root).get_trading_calendar()
    sus = S.StoreSuspendedDateSet(bars, cal, data_end=pd.Timestamp("2014-06-20"))
    dates = [dt.date(2014, 6, 13), dt.date(2014, 6, 16), dt.date(2014, 6, 17),
             dt.date(2014, 6, 14), dt.date(2014, 6, 2), dt.date(2014, 7, 1)]
    assert sus.contains("000001.XSHE", dates) == [False, True, False, False, False, False]
    assert sus.contains("999999.XSHE", [dt.date(2014, 6, 9)]) == [False]      # 上市前不算停牌
    assert sus.contains("123456.XSHE", [dt.date(2014, 6, 9)]) is None
