# coding: utf-8
"""净值指标单一口径(自 run_toy_backtest 抽出;回测运行器、交叉验证、面板共用)。
总收益 / 年化(按交易日数折算)/ 最大回撤 / 夏普(rf=0,日收益均值/标准差×√252)。"""
import numpy as np


def nav_stats(nav, periods_per_year=252):
    nav = nav.dropna()
    if len(nav) < 2:
        return {"total_return": np.nan, "cagr": np.nan, "max_drawdown": np.nan, "sharpe": np.nan}
    ret = nav.pct_change().dropna()
    total = nav.iloc[-1] / nav.iloc[0] - 1
    years = len(nav) / periods_per_year
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan
    dd = (nav / nav.cummax() - 1).min()
    sharpe = (ret.mean() / ret.std() * np.sqrt(periods_per_year)) if ret.std() > 0 else np.nan
    return {"total_return": float(total), "cagr": float(cagr), "max_drawdown": float(dd), "sharpe": float(sharpe)}
