# coding: utf-8
"""策略1 深跌反弹:纯信号逻辑在假 ctx 上锁死——买(回撤≥75%)/卖(反弹≥50%)/保留(之间)/成交额排序/新仓等额/已持仓不动/ST 剔除。"""
import numpy as np
import pandas as pd
import pytest

from strategies.dd_rebound.strategy import DdRebound

DATES = pd.bdate_range("2019-01-01", periods=30)


class FakeCtx:
    def __init__(self, close, amount, held=None, st=(), cons=None):
        self._close, self._amount, self._held, self._st = close, amount, held or {}, set(st)
        self._cons = cons

    def constituents(self, asof):
        return self._cons if self._cons is not None else sorted(self._close.columns)

    def is_st(self, symbol, asof):
        return symbol in self._st

    def panel(self, name, asof):
        return {"close": self._close, "amount": self._amount}[name].loc[:pd.Timestamp(asof)]

    def holdings(self):
        return dict(self._held)


def _pkg(**params):
    base = {"drawdown_buy": 0.75, "recover_sell": 0.50, "n_positions": 2, "volume_window": 5, "exclude_st": True}
    base.update(params)

    class Pkg:
        id, config = "dd_rebound", {"params": base, "benchmark": ["000300.SH"], "risk": {}, "type": "cross_sectional",
                                    "universe": {"boards": ["主板", "创业板"]}}
    return Pkg()


def _world():
    # A:高点 100 跌到 20(回撤 80%,可买);B:高点 100 跌到 30(回撤 70%,不可买);C:高点 100 现 55(反弹过半);
    # D:高点 100 现 40(介于 25%~50%);E:高点 100 跌到 24,成交额最大
    close = pd.DataFrame({"A": 100.0, "B": 100.0, "C": 100.0, "D": 100.0, "E": 100.0}, index=DATES)
    close.iloc[-1] = [20, 30, 55, 40, 24]
    amount = pd.DataFrame({"A": 1e6, "B": 5e6, "C": 1e6, "D": 1e6, "E": 9e6}, index=DATES)
    return close, amount


def test_buys_deepest_drawdowns_ranked_by_amount_equal_weight():
    close, amount = _world()
    w = DdRebound(_pkg()).signal(DATES[-1], FakeCtx(close, amount))
    assert w == {"E": 0.5, "A": 0.5}                      # 满足回撤≥75% 的只有 A、E;E 成交额大排前;各占 1/n


def test_keeps_held_between_thresholds_and_sells_recovered():
    close, amount = _world()
    held = {"C": 0.12, "D": 0.09}                         # C 已反弹到 55% → 卖;D 在 40% → 保留且权重不动
    w = DdRebound(_pkg()).signal(DATES[-1], FakeCtx(close, amount, held=held))
    assert w["D"] == 0.09 and "C" not in w
    assert w["E"] == 0.5 and len(w) == 2                  # 空位 1 个,只补成交额最大的 E


def test_excludes_st_and_names_out_of_universe():
    close, amount = _world()
    w = DdRebound(_pkg()).signal(DATES[-1], FakeCtx(close, amount, st=["E"]))
    assert list(w) == ["A"]                               # E 是 ST 不买;第二个空位没有候选 → 留现金
    held = {"D": 0.1}
    w = DdRebound(_pkg()).signal(DATES[-1], FakeCtx(close, amount, held=held, cons=["A", "B", "C", "E"]))
    assert "D" not in w                                   # D 退出 universe(退市/换板)→ 卖出


def test_high_is_running_max_up_to_asof_only():
    close, amount = _world()
    close.loc[DATES[-1], "A"] = 20.0
    close.loc[DATES[5], "A"] = 400.0                      # 更早的高点 400 → 现价 20 = 5%,仍可买
    future = close.copy(); future.loc[DATES[-1], "A"] = 20.0
    w = DdRebound(_pkg()).signal(DATES[-1], FakeCtx(close, amount))
    assert "A" in w
    assert np.isnan(DdRebound(_pkg()).signal(DATES[0], FakeCtx(close, amount)).get("A", np.nan))   # 首日无回撤 → 不买


def test_no_candidates_returns_only_kept():
    close, amount = _world()
    close.iloc[-1] = [60, 60, 60, 40, 60]
    w = DdRebound(_pkg()).signal(DATES[-1], FakeCtx(close, amount, held={"D": 0.1}))
    assert w == {"D": 0.1}
