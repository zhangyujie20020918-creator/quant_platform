# coding: utf-8
"""IC(Information Coefficient)检验:因子截面值与前瞻收益的 Spearman 秩相关(自 cb_quant 平移)。"""
import numpy as np
import pandas as pd
from scipy import stats

MIN_CROSS_SECTION = 3     # 截面有效样本少于此不算 IC(相关系数无意义);属机制常量,非协议阈值


def ic_series(factor_panel, forward_return_panel):
    """逐信号日截面 Spearman 秩相关 → Series(date → IC),升序。"""
    common = factor_panel.index.intersection(forward_return_panel.index)
    out = {}
    for d in common:
        both = pd.DataFrame({"f": factor_panel.loc[d], "r": forward_return_panel.loc[d]}).dropna()
        if len(both) < MIN_CROSS_SECTION:
            continue
        ic = both["f"].corr(both["r"], method="spearman")
        if pd.notna(ic):
            out[d] = float(ic)
    return pd.Series(out, dtype="float64").sort_index()


def ic_stats(ic):
    """IC 均值 / 标准差 / ICIR(均值/标准差)/ 正 IC 占比 / 有效截面数。"""
    ic = ic.dropna()
    n = len(ic)
    if n == 0:
        return {"ic_mean": np.nan, "ic_std": np.nan, "icir": np.nan, "positive_rate": np.nan, "n": 0}
    mean, std = float(ic.mean()), float(ic.std())
    return {"ic_mean": mean, "ic_std": std, "icir": mean / std if std and std > 0 else np.nan,
            "positive_rate": float((ic > 0).mean()), "n": n}


def ic_ttest(ic):
    """单样本 t 检验(H0: IC 均值 = 0)→ (t, 双尾 p);供 BH 校正。样本 <2 或 std=0 → (NaN, NaN)。"""
    ic = ic.dropna()
    if len(ic) < 2 or ic.std() == 0:
        return np.nan, np.nan
    t, p = stats.ttest_1samp(ic, 0.0)
    return float(t), float(p)
