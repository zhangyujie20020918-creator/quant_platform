# coding: utf-8
"""最小截面回测引擎测试(卡2 自研侧原型 / 卡3 种子)。
口径:T日信号→T+1开盘执行,等权,持有至下个调仓日,逐日按收盘估值,含佣金+滑点。"""
import numpy as np
import pandas as pd
import pytest

from backtest.engine import CostModel, run_backtest


def _panel(dates, symbols, values):
    return pd.DataFrame(values, index=pd.to_datetime(dates), columns=symbols)


# 5个交易日,2只股票
DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
NOCOST = CostModel(commission_rate=0.0, slippage_rate=0.0, min_commission=0.0)


def test_single_holding_nav_tracks_price_no_cost():
    opens = _panel(DATES, ["A"], [[10], [10], [11], [12], [13]])
    closes = _panel(DATES, ["A"], [[10], [10.5], [11.5], [12.5], [13.5]])
    # 调仓日 T=01-05 → T+1=01-06 开盘价10买入满仓A;持有到底
    res = run_backtest(rebalance_dates=["2026-01-05"], target_weights={"2026-01-05": {"A": 1.0}},
                       opens=opens, closes=closes, init_cash=10000.0, cost=NOCOST)
    nav = res["nav"]
    assert nav.index[0] == pd.Timestamp("2026-01-05")
    # 01-05 建仓前:全现金 10000
    assert nav.loc["2026-01-05"] == pytest.approx(10000.0)
    # 01-06 开盘10买入1000股(10000/10),当日收盘10.5 → 10500
    assert nav.loc["2026-01-06"] == pytest.approx(10500.0)
    # 01-09 收盘13.5 → 13500
    assert nav.loc["2026-01-09"] == pytest.approx(13500.0)


def test_equal_weight_two_names():
    opens = _panel(DATES, ["A", "B"], [[10, 20]] * 5)
    closes = _panel(DATES, ["A", "B"], [[10, 20], [11, 20], [11, 22], [11, 22], [11, 22]])
    res = run_backtest(["2026-01-05"], {"2026-01-05": {"A": 0.5, "B": 0.5}},
                       opens=opens, closes=closes, init_cash=10000.0, cost=NOCOST)
    # T+1开盘各投5000:A买500股@10,B买250股@20。01-06收盘 A=11→5500,B=20→5000 => 10500
    assert res["nav"].loc["2026-01-06"] == pytest.approx(10500.0)


def test_t_plus_1_open_execution_not_signal_day_close():
    opens = _panel(DATES, ["A"], [[10], [99], [99], [99], [99]])  # 若错用信号日执行会用别的价
    closes = _panel(DATES, ["A"], [[10], [99], [99], [99], [99]])
    res = run_backtest(["2026-01-05"], {"2026-01-05": {"A": 1.0}}, opens=opens, closes=closes,
                       init_cash=9900.0, cost=NOCOST)
    # T=01-05信号,T+1=01-06开盘价99买入 → 9900/99=100股;当日收盘99 → 9900,不亏不赚
    assert res["nav"].loc["2026-01-06"] == pytest.approx(9900.0)
    assert res["trades"].iloc[0]["price"] == pytest.approx(99.0)   # 用T+1开盘价,不是T收盘


def test_costs_reduce_nav():
    opens = _panel(DATES, ["A"], [[10]] * 5)
    closes = _panel(DATES, ["A"], [[10]] * 5)
    cost = CostModel(commission_rate=0.001, slippage_rate=0.002, min_commission=0.0)
    res = run_backtest(["2026-01-05"], {"2026-01-05": {"A": 1.0}}, opens=opens, closes=closes,
                       init_cash=10000.0, cost=cost)
    # 买入滑点抬价:10*(1+0.002)=10.02;佣金0.1%。价格不动,NAV应因成本略降
    assert res["nav"].loc["2026-01-06"] < 10000.0
    assert res["nav"].loc["2026-01-06"] > 9950.0


def test_rebalance_switches_holdings():
    opens = _panel(DATES, ["A", "B"], [[10, 10]] * 5)
    closes = _panel(DATES, ["A", "B"], [[10, 10]] * 5)
    res = run_backtest(["2026-01-05", "2026-01-07"],
                       {"2026-01-05": {"A": 1.0}, "2026-01-07": {"B": 1.0}},
                       opens=opens, closes=closes, init_cash=10000.0, cost=NOCOST)
    # 01-06买A;01-07信号换B→01-08开盘卖A买B。价格恒10,无成本 → NAV恒10000
    assert res["nav"].loc["2026-01-09"] == pytest.approx(10000.0)
    sides = res["trades"]["side"].tolist()
    assert "buy" in sides and "sell" in sides
    held_end = res["positions_end"]
    assert "B" in held_end and "A" not in held_end


def test_missing_price_skips_symbol_no_crash():
    opens = _panel(DATES, ["A", "B"], [[10, np.nan]] * 5)   # B无开盘价(停牌)
    closes = _panel(DATES, ["A", "B"], [[10, np.nan]] * 5)
    res = run_backtest(["2026-01-05"], {"2026-01-05": {"A": 0.5, "B": 0.5}},
                       opens=opens, closes=closes, init_cash=10000.0, cost=NOCOST)
    # B买不进(无价),只买A;不崩溃
    assert "A" in res["positions_end"] and "B" not in res["positions_end"]


def test_missing_close_marks_position_at_last_known_price():
    opens = _panel(DATES, ["A"], [[10]] * 5)
    closes = _panel(DATES, ["A"], [[10], [11], [np.nan], [12], [12]])   # 01-07 停牌无收盘
    res = run_backtest(["2026-01-05"], {"2026-01-05": {"A": 1.0}}, opens=opens, closes=closes,
                       init_cash=10000.0, cost=NOCOST)
    # 停牌日持仓按末次有效价 11 估值(1000 股 → 11000),而不是按 0 计后次日"暴涨"回来
    assert res["nav"].loc["2026-01-07"] == pytest.approx(11000.0)
    assert res["nav"].loc["2026-01-08"] == pytest.approx(12000.0)


def test_nav_and_returns_shapes():
    opens = _panel(DATES, ["A"], [[10]] * 5)
    closes = _panel(DATES, ["A"], [[10, 11, 12, 13, 14]][0] and [[10], [11], [12], [13], [14]])
    res = run_backtest(["2026-01-05"], {"2026-01-05": {"A": 1.0}}, opens=opens, closes=closes,
                       init_cash=1000.0, cost=NOCOST)
    assert list(res["nav"].index) == list(pd.to_datetime(DATES))
    assert res["nav"].notna().all()
