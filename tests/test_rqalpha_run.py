# coding: utf-8
"""端到端:RQAlpha 引擎通过 mod 注入 StoreDataSource,在合成 store 上跑完整回测(无 bundle)。
核对:成交价 = 我们的原始收盘;持仓过除权日按因子比例调股数、市值连续;停牌日下单被拒;ST 标记可查;基准来自 index_daily。"""
import datetime as dt
import os

import pandas as pd
import pytest
import yaml
from rqalpha import run_func
from rqalpha.apis import is_st_stock, order_shares

from tests.rq_seed import F_AFTER, F_BEFORE, seed


ST_SEEN = {}     # handle_bar 旁路记录 is_st_stock 结果,run_func 结束后由测试核对


def init(context):
    context.s = "000001.XSHE"
    context.bought = False


def handle_bar(context, bar_dict):
    today = context.now.date()
    if not context.bought:
        order_shares(context.s, 10000)
        context.bought = True
    if today in (dt.date(2014, 6, 9), dt.date(2014, 6, 10)):
        ST_SEEN[today] = is_st_stock("000005.XSHE")
    if today in (dt.date(2014, 6, 16), dt.date(2014, 6, 17)):      # 06-16 停牌 → 拒单;06-17 成交
        order_shares(context.s, -100)


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("rq_run"))
    cfg = seed(root)
    cfg_path = os.path.join(root, "config.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)
    config = {
        "base": {"start_date": "2014-06-04", "end_date": "2014-06-20", "accounts": {"stock": 1_000_000},
                 "data_bundle_path": os.path.join(root, "no_bundle_here")},
        "extra": {"log_level": "error"},
        "mod": {
            "store": {"enabled": True, "lib": "backtest.rqalpha_adapter.mod",
                      "root": root, "config_path": cfg_path, "preload": ["000001.SZ"]},
            "sys_progress": {"enabled": False},
            "sys_analyser": {"enabled": True, "plot": False, "benchmark": "000300.XSHG"},
        },
    }
    res = run_func(init=init, handle_bar=handle_bar, config=config)
    return res["sys_analyser"]


def test_trade_price_is_our_raw_close(result):
    trades = result["trades"]
    first = trades.iloc[0]
    assert first["last_price"] == 11.30 and first["last_quantity"] == 10000     # 06-04 收盘(原始价)


def test_position_scaled_by_factor_ratio_on_ex_date(result):
    pos = result["stock_positions"].reset_index()
    q = pos.set_index(pos["date"].dt.date)["quantity"]
    assert q[dt.date(2014, 6, 11)] == 10000
    assert q[dt.date(2014, 6, 12)] == round(10000 * F_AFTER / F_BEFORE)        # 12170


def test_market_value_continuous_across_ex_date(result):
    pos = result["stock_positions"].reset_index()
    mv = pos.set_index(pos["date"].dt.date)["market_value"]
    expected = round(10000 * F_AFTER / F_BEFORE) * 9.71
    assert mv[dt.date(2014, 6, 12)] == pytest.approx(expected, rel=1e-9)
    # 除权日的市值变动 = 除权后股价相对"除权昨收"的涨幅,而非 11.78→9.71 的假暴跌
    assert mv[dt.date(2014, 6, 12)] / mv[dt.date(2014, 6, 11)] == pytest.approx(
        (F_AFTER / F_BEFORE) * 9.71 / 11.78, rel=1e-3)


def test_suspended_day_order_rejected_next_day_fills(result):
    trades = result["trades"]
    sells = trades[trades["side"] == "SELL"]
    assert pd.to_datetime(sells["trading_datetime"]).dt.date.tolist() == [dt.date(2014, 6, 17)]
    assert sells.iloc[0]["last_price"] == 10.20


def test_st_api_reads_namechange(result):
    assert ST_SEEN == {dt.date(2014, 6, 9): False, dt.date(2014, 6, 10): True}


def test_benchmark_from_index_daily(result):
    b = result["benchmark_portfolio"]
    # RQAlpha 基准首日收益从回测前一交易日收盘(06-03:2100)起算
    assert b["unit_net_value"].iloc[-1] == pytest.approx(2113.0 / 2100.0, rel=1e-9)
