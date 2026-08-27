# coding: utf-8
"""A股股票品种包 · 真实性红线验收测试(蓝图第七节:每条红线至少一个验收测试;清单见 instruments/cn_stock_redlines.md)。

一次合成 store 回测里按日期触发全部场景,RQAlpha 内置规则 + 我们的数据 + 品种规则表成本:
  R1 前复权正确 | R2 涨停不可买 / 跌停不可卖 | R3 停牌不可交易(口径书面声明) | R4 ST 可识别可过滤
  R5 退市股在历史池 + 退市清算 | R6 T+1 | R7 全成本(佣金/最低佣金/印花税/过户费按品种规则表)
"""
import datetime as dt
import os

import pandas as pd
import pytest
import yaml
from rqalpha import run_func
from rqalpha.apis import history_bars, instruments, is_st_stock, order_shares

from tests.rq_seed import F_AFTER, F_BEFORE, seed

RECORD = {}
D = dt.date


def init(context):
    ins = instruments("600999.XSHG")
    RECORD["delisted_instrument"] = (ins.status, ins.de_listed_date.date())


def handle_bar(context, bar_dict):
    today = context.now.date()
    if today == D(2014, 6, 4):
        order_shares("000001.XSHE", 10000)            # R7 成本样本 + R3 停牌样本(06-16)
        order_shares("600999.XSHG", 1000)             # R5 退市清算样本
    if today == D(2014, 6, 5):                        # R6:当日买入当日卖 → 拒;次日卖 → 成
        order_shares("600000.XSHG", 1000)
        order_shares("600000.XSHG", -1000)
    if today == D(2014, 6, 6):
        order_shares("600000.XSHG", -1000)
    if today == D(2014, 6, 10):                       # R2:涨停收盘买 → 拒;R4:ST 过滤
        order_shares("300001.XSHE", 100)
        RECORD["st_filtered"] = [o for o in ["000005.XSHE", "600000.XSHG"] if not is_st_stock(o)]
    if today == D(2014, 6, 11):
        order_shares("300001.XSHE", 100)              # 非涨停日 → 成
    if today == D(2014, 6, 12):                       # R1:前复权
        RECORD["pre_adj"] = history_bars("000001.XSHE", 2, "1d", "close").tolist()
        RECORD["raw"] = history_bars("000001.XSHE", 2, "1d", "close", adjust_type="none").tolist()
    if today == D(2014, 6, 13):
        order_shares("300001.XSHE", -100)             # 跌停收盘卖 → 拒
    if today == D(2014, 6, 16):
        order_shares("300001.XSHE", -100)             # 非跌停日 → 成
        order_shares("000001.XSHE", -100)             # R3:停牌 → 拒
    if today == D(2014, 6, 17):
        order_shares("000001.XSHE", -100)             # 复牌 → 成(R7 卖出成本样本)


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("rq_redline"))
    cfg = seed(root)
    cfg_path = os.path.join(root, "config.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)
    config = {
        "base": {"start_date": "2014-06-04", "end_date": "2014-06-20", "accounts": {"stock": 1_000_000},
                 "data_bundle_path": os.path.join(root, "no_bundle_here")},
        "extra": {"log_level": "error"},
        "mod": {
            "store": {"enabled": True, "lib": "backtest.rqalpha_adapter.mod", "root": root, "config_path": cfg_path},
            "sys_progress": {"enabled": False},
            "sys_analyser": {"enabled": True, "plot": False},
        },
    }
    res = run_func(init=init, handle_bar=handle_bar, config=config)["sys_analyser"]
    trades = res["trades"].copy()
    trades["day"] = pd.to_datetime(trades["trading_datetime"]).dt.date
    return res, trades


def _trades_of(trades, obid):
    t = trades[trades["order_book_id"] == obid]
    return [(r["day"], r["side"], r["last_price"], r["last_quantity"]) for _, r in t.iterrows()]


# R1 前复权正确(头号未来函数源):查询日前的价格按查询日因子重基
def test_r1_pre_adjust_rebases_history_on_query_date(result):
    assert RECORD["pre_adj"][0] == pytest.approx(11.78 * F_BEFORE / F_AFTER, abs=1e-9)
    assert RECORD["pre_adj"][1] == 9.71 and RECORD["raw"] == [11.78, 9.71]


# R2 涨停不可买、跌停不可卖(RQAlpha price_limit + 我们按品种规则表算的 limit_up/limit_down)
def test_r2_limit_up_buy_and_limit_down_sell_rejected(result):
    _, trades = result
    assert _trades_of(trades, "300001.XSHE") == [(D(2014, 6, 11), "BUY", 22.0, 100), (D(2014, 6, 16), "SELL", 18.0, 100)]


# R3 停牌口径:缺行 = 停牌,当日不可交易
def test_r3_suspended_day_rejected(result):
    _, trades = result
    sells = [t for t in _trades_of(trades, "000001.XSHE") if t[1] == "SELL"]
    assert sells == [(D(2014, 6, 17), "SELL", 10.20, 100)]


# R4 ST 过滤:策略层可按 namechange 区间剔除
def test_r4_st_filter(result):
    assert RECORD["st_filtered"] == ["600000.XSHG"]


# R5 退市股在历史池 + 退市清算(RQAlpha 在退市前最后一个交易日结算时按末价折成现金,不凭空消失)
def test_r5_delisted_in_pool_and_cash_returned(result):
    res, _ = result
    assert RECORD["delisted_instrument"] == ("Delisted", D(2014, 6, 18))
    pos = res["stock_positions"]
    assert pos[pos["order_book_id"] == "600999.XSHG"].index.max().date() == D(2014, 6, 16)   # 06-17 结算时已清
    p = res["portfolio"]
    cash = p["cash"]
    c16, c17 = cash[cash.index.date == D(2014, 6, 16)].iloc[0], cash[cash.index.date == D(2014, 6, 17)].iloc[0]
    # 06-17 现金变动 = 卖 100 股 000001(1020 − 佣金 5 − 印花税 1.02)+ 600999 退市折现 1000×5.0
    assert c17 - c16 == pytest.approx(1020 - 5 - 1.02 + 5000, abs=1e-6)


# R6 T+1:当日买入不可当日卖出
def test_r6_t_plus_1(result):
    _, trades = result
    assert _trades_of(trades, "600000.XSHG") == [(D(2014, 6, 5), "BUY", 10.0, 1000), (D(2014, 6, 6), "SELL", 10.0, 1000)]


# R7 全成本:佣金万2(最低 5 元)+ 卖出印花税 0.1%(2014)+ 过户费(2014 尚无)——全部来自品种规则表,非 RQAlpha 默认万8/0.05%
def test_r7_costs_from_rule_table(result):
    _, trades = result
    t = trades[trades["order_book_id"] == "000001.XSHE"]
    buy = t[t["side"] == "BUY"].iloc[0]
    assert buy["commission"] == pytest.approx(10000 * 11.30 * 0.0002) and buy["tax"] == 0
    sell = t[t["side"] == "SELL"].iloc[0]
    assert sell["commission"] == 5.0                                   # 1020 元 × 万2 = 0.204 < 最低 5 元
    assert sell["tax"] == pytest.approx(100 * 10.20 * 0.001)
    assert sell["transaction_cost"] == pytest.approx(5.0 + 1.02)
