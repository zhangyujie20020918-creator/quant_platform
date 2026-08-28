# coding: utf-8
"""分组检验:逐信号日按因子值分 N 组,看组均前瞻收益是否单调;top 组换手衡量交易成本敏感度。"""
import numpy as np
import pandas as pd


def _groups(values, n_quantiles):
    """因子截面 → 组号 Series(1=最低 … n=最高);样本不足或无法分组返回 None。"""
    f = values.dropna()
    if len(f) < n_quantiles:
        return None
    try:
        g = pd.qcut(f, n_quantiles, labels=False, duplicates="drop")
    except ValueError:
        return None
    return (g + 1).astype(int)


def quantile_returns(factor_panel, forward_return_panel, n_quantiles):
    """DataFrame(date × 组号):各组等权平均前瞻收益;当日可分组标的不足则跳过该日。"""
    common = factor_panel.index.intersection(forward_return_panel.index)
    rows = []
    for d in common:
        g = _groups(factor_panel.loc[d], n_quantiles)
        if g is None:
            continue
        r = forward_return_panel.loc[d]
        row = {}
        for k in sorted(g.unique()):
            rets = r.reindex(g[g == k].index).dropna()
            row[int(k)] = float(rets.mean()) if len(rets) else np.nan
        rows.append(pd.Series(row, name=d))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_index()


def monotonicity(quantile_return_panel):
    """组序号 vs 各组全期平均收益的 Spearman 相关(−1~1);组数 <3 无意义 → NaN。"""
    if quantile_return_panel is None or quantile_return_panel.empty:
        return np.nan
    avg = quantile_return_panel.mean().sort_index()
    if len(avg) < 3:
        return np.nan
    rank = pd.Series(range(1, len(avg) + 1), index=avg.index, dtype=float)
    return float(rank.corr(avg, method="spearman"))


def top_group_turnover(factor_panel, n_quantiles):
    """相邻信号日 top 组(因子最高组)成员被替换的比例 → Series(date → 换手);首个信号日无前值不计。"""
    prev, out = None, {}
    for d in factor_panel.index:
        g = _groups(factor_panel.loc[d], n_quantiles)
        if g is None:
            continue
        top = set(g[g == g.max()].index)
        if prev is not None and top:
            out[d] = 1.0 - len(top & prev) / len(top)
        prev = top
    return pd.Series(out, dtype="float64").sort_index()
