# coding: utf-8
"""策略包契约(蓝图原则5/6):两原型基类、包格式校验、build、风控参数、玩具策略纯信号逻辑。"""
import os
import textwrap

import numpy as np
import pandas as pd
import pytest
import yaml

from core.calendar import TradingCalendar
from strategies.base import CrossSectionalStrategy, TimeSeriesStrategy
from strategies.package import PackageError, build_strategy, load_package
from strategies.risk import apply_risk
from strategies.toy_lowvol.strategy import ToyLowVol

GOOD = {
    "id": "fixed_mix", "name": "固定比例", "type": "time_series",
    "universe": {"symbols": ["511010.SH", "000300.SH"]},
    "params": {"rebalance": "monthly_first", "w_bond": 0.6},
    "benchmark": ["000300.SH"], "risk": {"max_weight": 1.0, "max_positions": 10},
    "crash_definition": ["回撤 > 20%"], "status": "toy",
}
STRATEGY_PY = textwrap.dedent('''
    from strategies.base import TimeSeriesStrategy

    class FixedMix(TimeSeriesStrategy):
        def signal(self, asof, ctx):
            w = self.params["w_bond"]
            return {"511010.SH": w, "000300.SH": round(1 - w, 6)}

    def build(package):
        return FixedMix(package)
''')


def _pkg(tmp_path, cfg=GOOD, code=STRATEGY_PY):
    d = tmp_path / "pkgs" / cfg["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    (d / "strategy.py").write_text(code, encoding="utf-8")
    return str(tmp_path / "pkgs")


def test_load_package_reads_config(tmp_path):
    root = _pkg(tmp_path)
    pkg = load_package("fixed_mix", root=root)
    assert pkg.id == "fixed_mix" and pkg.config["params"]["w_bond"] == 0.6 and pkg.dir.endswith("fixed_mix")


@pytest.mark.parametrize("bad", [
    {k: v for k, v in GOOD.items() if k != "crash_definition"},        # 崩溃定义缺失(SOP S5 三件套)
    dict(GOOD, type="event"),                                           # 原型类型非法
    dict(GOOD, benchmark=[]),                                           # 基准必须 ≥1(原则6)
    dict(GOOD, status="approved"),                                      # approved 必须有 approved_by(人类签字)
    dict(GOOD, status="live"),
])
def test_load_package_rejects_invalid_config(tmp_path, bad):
    root = _pkg(tmp_path, bad)
    with pytest.raises(PackageError):
        load_package("fixed_mix", root=root)


def test_load_package_missing_dir(tmp_path):
    with pytest.raises(PackageError):
        load_package("nope", root=str(tmp_path))


def test_build_strategy_from_package_dir_time_series(tmp_path):
    root = _pkg(tmp_path)
    s = build_strategy(load_package("fixed_mix", root=root))
    assert isinstance(s, TimeSeriesStrategy) and s.type == "time_series" and s.id == "fixed_mix"
    assert s.signal(pd.Timestamp("2026-01-05"), ctx=None) == {"511010.SH": 0.6, "000300.SH": 0.4}
    assert s.benchmark == ["000300.SH"]


def test_rebalance_days_come_from_core_calendar(tmp_path):
    root = _pkg(tmp_path)
    s = build_strategy(load_package("fixed_mix", root=root))
    cal = TradingCalendar(days=pd.bdate_range("2026-01-05", "2026-03-31"), source="file")
    days = s.rebalance_days(cal, "2026-01-01", "2026-03-31")
    assert list(days) == list(pd.to_datetime(["2026-01-05", "2026-02-02", "2026-03-02"]))


# ---------- 风控参数 ----------

def test_apply_risk_caps_weight_and_truncates_positions():
    w = {"a": 0.5, "b": 0.3, "c": 0.2}
    assert apply_risk(w, {"max_weight": 0.4, "max_positions": 2}) == {"a": 0.4, "b": 0.3}
    assert apply_risk(w, {"max_weight": 1.0, "max_positions": 10}) == w
    assert apply_risk({}, {"max_weight": 0.4, "max_positions": 2}) == {}


def test_apply_risk_keeps_signal_order_for_equal_weights():
    # 等权并列时保持策略给出的顺序(选券优先级),不得按 symbol 重排——买入顺序影响现金约束下的成交
    w = {"600000.SH": 0.5, "000001.SZ": 0.5}
    assert list(apply_risk(w, {"max_weight": 1.0, "max_positions": 10})) == ["600000.SH", "000001.SZ"]


# ---------- 玩具策略纯信号逻辑(引擎无关) ----------

class FakeCtx:
    def __init__(self, closes, st=()):
        self._c, self._st = closes, set(st)

    def constituents(self, asof):
        return sorted(self._c)

    def is_st(self, symbol, asof):
        return symbol in self._st

    def closes(self, symbol, asof, n):
        return np.asarray(self._c[symbol][-n:], dtype=float)


def _toy(params):
    class Pkg:
        id, config = "toy", {"params": params, "benchmark": ["000300.SH"], "risk": {}, "type": "cross_sectional",
                             "universe": {"index": "000300.SH"}}
    return ToyLowVol(Pkg())


def test_toy_lowvol_picks_lowest_vol_and_filters_st():
    closes = {"A": [10, 12, 9, 13], "B": [10, 10.2, 9.9, 10.1], "C": [5, 5, 5, 5]}
    ctx = FakeCtx(closes, st=["C"])
    assert _toy({"n_select": 1, "lookback": 3, "filter_st": True}).signal("2026-01-05", ctx) == {"B": 1.0}
    assert _toy({"n_select": 1, "lookback": 3, "filter_st": False}).signal("2026-01-05", ctx) == {"C": 1.0}
    assert _toy({"n_select": 2, "lookback": 3, "filter_st": True}).signal("2026-01-05", ctx) == {"B": 0.5, "A": 0.5}


def test_toy_lowvol_skips_names_with_insufficient_history():
    ctx = FakeCtx({"A": [10, 11], "B": [10, 10, 10, 10]})
    assert _toy({"n_select": 2, "lookback": 3, "filter_st": False}).signal("2026-01-05", ctx) == {"B": 1.0}


def test_real_toy_lowvol_package_is_valid_and_not_approved():
    pkg = load_package("toy_lowvol")
    s = build_strategy(pkg)
    assert isinstance(s, CrossSectionalStrategy) and pkg.config["status"] == "toy" and pkg.config["benchmark"]
    assert pkg.config["crash_definition"] and os.path.exists(os.path.join(pkg.dir, "说明书.md"))


def test_package_execution_and_costs_sections_validated(tmp_path):
    cfg = dict(GOOD, execution={"mode": "next_close", "slippage": 0.02},
               costs={"commission_rate": 0.005, "min_commission": 0.0, "stamp_tax_sell": [], "transfer_fee": []})
    pkg = load_package("fixed_mix", root=_pkg(tmp_path, cfg))
    assert pkg.config["execution"]["mode"] == "next_close"
    with pytest.raises(PackageError):
        load_package("fixed_mix", root=_pkg(tmp_path, dict(GOOD, execution={"mode": "same_close"})))
    assert load_package("fixed_mix", root=_pkg(tmp_path, GOOD)).config["execution"] == {"mode": "next_open", "slippage": 0.0}


def test_apply_param_overrides_returns_new_config_without_touching_package(tmp_path):
    from strategies.package import apply_overrides
    pkg = load_package("fixed_mix", root=_pkg(tmp_path))
    new = apply_overrides(pkg.config, {"params.w_bond": 0.3, "execution.slippage": 0.01})
    assert new["params"]["w_bond"] == 0.3 and new["execution"]["slippage"] == 0.01
    assert pkg.config["params"]["w_bond"] == 0.6                                   # 原包不动
    with pytest.raises(PackageError):
        apply_overrides(pkg.config, {"params.not_exist": 1})                      # 不存在的键拒绝(防拼错静默)
