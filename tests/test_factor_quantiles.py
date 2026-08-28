# coding: utf-8
"""分组检验:逐信号日按因子分 N 组的组均前瞻收益、单调性(组序号 vs 组均收益的 Spearman)、top 组换手。"""
import numpy as np
import pandas as pd
import pytest

from factors.quantiles import monotonicity, quantile_returns, top_group_turnover

D = pd.to_datetime(["2026-01-05", "2026-02-02", "2026-03-02"])
SYMS = list("ABCDEF")


def test_quantile_returns_groups_by_factor_and_averages_forward_returns():
    f = pd.DataFrame([[1, 2, 3, 4, 5, 6]] * 3, index=D, columns=SYMS, dtype=float)
    r = pd.DataFrame([[0.01, 0.02, 0.03, 0.04, 0.05, 0.06]] * 3, index=D, columns=SYMS)
    qr = quantile_returns(f, r, n_quantiles=3)
    assert list(qr.columns) == [1, 2, 3]
    assert qr.loc[D[0]].tolist() == pytest.approx([0.015, 0.035, 0.055])   # 组1=因子最低两只


def test_quantile_returns_skips_dates_with_too_few_names():
    f = pd.DataFrame([[1, 2, np.nan, np.nan, np.nan, np.nan]] * 3, index=D, columns=SYMS)
    r = pd.DataFrame(0.01, index=D, columns=SYMS)
    assert quantile_returns(f, r, n_quantiles=3).empty


def test_monotonicity_is_spearman_between_group_rank_and_mean_return():
    qr = pd.DataFrame({1: [0.01, 0.02], 2: [0.02, 0.03], 3: [0.03, 0.04]}, index=D[:2])
    assert monotonicity(qr) == pytest.approx(1.0)
    qr_rev = pd.DataFrame({1: [0.03, 0.04], 2: [0.02, 0.03], 3: [0.01, 0.02]}, index=D[:2])
    assert monotonicity(qr_rev) == pytest.approx(-1.0)
    assert np.isnan(monotonicity(pd.DataFrame({1: [0.1], 2: [0.2]}, index=D[:1])))   # <3 组无意义


def test_top_group_turnover_is_fraction_of_members_replaced():
    f = pd.DataFrame([[1, 2, 3, 4, 5, 6], [1, 2, 3, 6, 5, 4], [6, 5, 4, 3, 2, 1]], index=D, columns=SYMS, dtype=float)
    # 3 组,top 组 = 因子最高两只:01-05 {E,F};02-02 {D,E} → 换 1/2;03-02 {A,B} → 换 2/2
    to = top_group_turnover(f, n_quantiles=3)
    assert to.loc[D[1]] == pytest.approx(0.5) and to.loc[D[2]] == pytest.approx(1.0)
    assert D[0] not in to.index
