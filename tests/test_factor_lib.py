# coding: utf-8
"""因子实现库 factors/lib:统一签名 compute(ctx) → DataFrame(date×symbol),向量化,rolling 按 min_periods 规则。"""
import math

import numpy as np
import pandas as pd
import pytest

from factors.lib import load_factor

CFG = {"protocol": {"min_periods_ratio": 0.6, "negative_control_seed": 7}}
DATES = pd.bdate_range("2026-01-01", periods=130)


def _ctx(close):
    return {"close": close, "open": close, "cfg": CFG}


def test_vol_20_is_rolling_std_of_log_returns_with_min_periods():
    a = pd.Series(100.0 * np.exp(np.cumsum([0.01, -0.01] * 65)), index=DATES)     # 交替 ±1% → 波动恒定
    close = pd.DataFrame({"A": a, "B": 50.0})
    out = load_factor("vol_20").compute(_ctx(close))
    assert out.shape == close.shape
    assert np.isnan(out["A"].iloc[10])                                            # 不足 ceil(20×0.6)=12 个收益
    assert out["A"].iloc[40] == pytest.approx(np.std([0.01, -0.01] * 10, ddof=1))
    assert out["B"].iloc[40] == pytest.approx(0.0)


def test_rev_20_is_20_day_return():
    close = pd.DataFrame({"A": np.linspace(100, 229, 130)}, index=DATES)
    out = load_factor("rev_20").compute(_ctx(close))
    assert out["A"].iloc[20] == pytest.approx(close["A"].iloc[20] / close["A"].iloc[0] - 1)
    assert np.isnan(out["A"].iloc[19])


def test_mom_120_20_skips_last_month():
    close = pd.DataFrame({"A": np.linspace(100, 229, 130)}, index=DATES)
    out = load_factor("mom_120_20").compute(_ctx(close))
    assert out["A"].iloc[120] == pytest.approx(close["A"].iloc[100] / close["A"].iloc[0] - 1)
    assert np.isnan(out["A"].iloc[119])


def test_random_control_is_seeded_and_masks_missing_prices():
    close = pd.DataFrame({"A": 1.0, "B": [np.nan] * 5 + [1.0] * 125}, index=DATES)
    r1 = load_factor("random_control").compute(_ctx(close))
    r2 = load_factor("random_control").compute(_ctx(close))
    assert r1.equals(r2) and r1["B"].iloc[:5].isna().all() and r1["A"].notna().all()
    assert r1["A"].std() > 0


def test_unknown_factor_id_raises():
    with pytest.raises(KeyError):
        load_factor("nope_123")


def test_min_periods_rule():
    from factors.lib import min_periods
    assert min_periods(20, CFG) == math.ceil(20 * 0.6) == 12
