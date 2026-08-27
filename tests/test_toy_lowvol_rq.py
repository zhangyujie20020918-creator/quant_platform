# coding: utf-8
"""玩具策略 RQAlpha 版:信号 T 收盘(月/周首交易日)→ T+1 集合竞价先卖后买;选券逻辑与自研共用 select_low_vol。
合成 store:成分 000001/000005/600000(2014-05-30 快照),lookback=3,n=1,周频 → 信号日 06-04(历史不足)、06-09、06-16。"""
import datetime as dt
import os

import pandas as pd
import pytest
import yaml
from rqalpha import run_func

from strategies.toy_lowvol_rq import make_strategy, plan_rebalance
from tests.rq_seed import seed

D = dt.date
COSTS_ALIGN = {"commission_rate": 0.0002, "min_commission": 0.0, "stamp_tax_sell": [], "transfer_fee": []}


# ---------- 纯函数:调仓计划(先清非目标 → 减仓 → 按剩余现金依次买入,整手) ----------

def test_plan_rebalance_sells_first_then_buys_within_expected_cash():
    orders = plan_rebalance(cash=200.0, positions={"A": 1000}, opens={"A": 10.0, "B": 5.0},
                            target={"B": 1.0}, costs=COSTS_ALIGN, round_lot=100)
    # 卖 A 1000 股得 10000×(1−0.0002)=9998 → 现金 10198;买 B:权益 10200×1.0=10200,预算 min(10200, 10198)
    # → 10198/(5×1.0002)=2039.19 → 整手 2000 股
    assert orders == [("A", -1000), ("B", 2000)]


def test_plan_rebalance_skips_names_without_open_price_and_zero_lots():
    orders = plan_rebalance(cash=1000.0, positions={"A": 100}, opens={"A": float("nan"), "B": 5.0},
                            target={"B": 0.05}, costs=COSTS_ALIGN, round_lot=100)
    # A 无价不卖;B 目标 (1000+0)×0.05=50 元 → 不足一手 → 不下单
    assert orders == []


def test_plan_rebalance_trims_over_weight_position():
    orders = plan_rebalance(cash=0.0, positions={"A": 1000}, opens={"A": 10.0},
                            target={"A": 0.5}, costs=COSTS_ALIGN, round_lot=100)
    assert orders == [("A", -500)]


# ---------- 端到端 ----------

def _run(root, cfg, filter_st):
    cfg_path = os.path.join(root, "config.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)
    params = {"index": "000300.SH", "n_select": 1, "lookback": 3, "rebalance": "weekly_first", "filter_st": filter_st,
              "costs": COSTS_ALIGN}
    funcs = make_strategy(params, cfg=cfg, root=root)
    state = funcs.pop("state")
    config = {
        "base": {"start_date": "2014-06-04", "end_date": "2014-06-20", "accounts": {"stock": 1_000_000},
                 "data_bundle_path": os.path.join(root, "no_bundle_here")},
        "extra": {"log_level": "error"},
        "mod": {
            "store": {"enabled": True, "lib": "backtest.rqalpha_adapter.mod", "root": root, "config_path": cfg_path,
                      "costs": COSTS_ALIGN},
            "sys_progress": {"enabled": False},
            "sys_analyser": {"enabled": True, "plot": False},
        },
    }
    res = run_func(config=config, **funcs)["sys_analyser"]
    # 周首交易日信号:06-04(历史不足 → 空选)、06-09、06-16
    assert state["signals"] == 3 and sorted(state["picks"]) == [D(2014, 6, 4), D(2014, 6, 9), D(2014, 6, 16)]
    assert state["picks"][D(2014, 6, 4)] == {}
    t = res["trades"]
    return [(pd.Timestamp(r["trading_datetime"]).date(), r["order_book_id"], r["side"], r["last_price"], r["last_quantity"])
            for _, r in t.iterrows()]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("rq_toy"))
    return root, seed(root)


def test_signal_at_close_executes_next_open_lowest_vol_pick(world):
    root, cfg = world
    trades = _run(root, cfg, filter_st=False)
    # 06-09 信号:000005/600000 波动为 0(并列),按成分顺序取 000005;06-10 开盘 3.0 买入整手 333200 股
    assert trades == [(D(2014, 6, 10), "000005.XSHE", "BUY", 3.0, 333200)]


def test_st_filter_switches_pick_and_rebalances(world):
    root, cfg = world
    trades = _run(root, cfg, filter_st=True)
    # 06-16 信号:000005 已 ST → 剔除 → 换 600000;06-17 先卖后买
    assert trades == [(D(2014, 6, 10), "000005.XSHE", "BUY", 3.0, 333200),
                      (D(2014, 6, 17), "000005.XSHE", "SELL", 3.0, 333200),
                      (D(2014, 6, 17), "600000.XSHG", "BUY", 10.0, 99900)]
