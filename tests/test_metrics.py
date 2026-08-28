# coding: utf-8
"""净值指标单一口径(backtest/metrics.py):总收益 / 年化 / 最大回撤 / 夏普(rf=0)。"""
import numpy as np
import pandas as pd
import pytest

from backtest.metrics import nav_stats


def test_nav_stats_basic():
    nav = pd.Series([100.0, 110.0, 99.0, 120.0], index=pd.bdate_range("2026-01-05", periods=4))
    st = nav_stats(nav)
    assert st["total_return"] == pytest.approx(0.2)
    assert st["max_drawdown"] == pytest.approx(99 / 110 - 1)
    assert st["cagr"] == pytest.approx(1.2 ** (252 / 4) - 1)
    assert np.isfinite(st["sharpe"])


def test_nav_stats_constant_series_has_nan_sharpe():
    nav = pd.Series([1.0, 1.0, 1.0], index=pd.bdate_range("2026-01-05", periods=3))
    st = nav_stats(nav)
    assert st["total_return"] == 0 and st["max_drawdown"] == 0 and np.isnan(st["sharpe"])
