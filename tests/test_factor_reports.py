# coding: utf-8
"""alphalens / quantstats 薄封装:价格口径在入口锁死(T+1 开盘),产出落文件。"""
import os

import numpy as np
import pandas as pd

from backtest.quantstats_report import nav_report
from factors.alphalens_wrapper import locked_prices, tear_sheet

DATES = pd.bdate_range("2024-01-01", periods=160)
SYMS = [f"S{i:02d}" for i in range(12)]


def _prices(seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (len(DATES), len(SYMS))), axis=0)),
                        index=DATES, columns=SYMS)


def test_locked_prices_are_next_day_opens():
    opens = _prices()
    lp = locked_prices(opens)
    assert lp.iloc[0].equals(opens.iloc[1]) and lp.iloc[-1].isna().all()


def test_tear_sheet_writes_figures_and_tables(tmp_path):
    opens = _prices()
    factor = pd.DataFrame(np.random.default_rng(1).normal(size=opens.shape), index=DATES, columns=SYMS)
    files = tear_sheet(factor.iloc[::5], opens, str(tmp_path), periods=(1, 5, 20), quantiles=3)
    assert any(f.endswith(".png") for f in files) and any(f.endswith(".csv") for f in files)
    assert all(os.path.exists(f) for f in files)


def test_quantstats_nav_report_writes_html(tmp_path):
    nav = pd.Series(np.cumprod(1 + np.random.default_rng(2).normal(0.0003, 0.01, len(DATES))), index=DATES)
    bench = pd.Series(np.cumprod(1 + np.random.default_rng(3).normal(0.0002, 0.01, len(DATES))), index=DATES)
    out = nav_report(nav, bench, os.path.join(str(tmp_path), "qs.html"), title="toy")
    assert os.path.exists(out) and os.path.getsize(out) > 10_000
