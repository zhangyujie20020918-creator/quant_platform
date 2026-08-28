# coding: utf-8
"""Benjamini-Hochberg 多重比较校正(自 cb_quant 平移)。

一批 N 个因子一起测,单因子阈值不是为"同时测 N 次"校准的,纯靠运气也会冒出假阳性;
裁决前对各因子样本内 IC 的 t 检验 p 值做一次 BH 校正(FDR = config protocol.bh_alpha)。
"""
import numpy as np


def benjamini_hochberg(p_values, fdr):
    """p_values: {label: p(双尾)} → {label: {"p_adj": 校正后 p, "reject": 是否在 fdr 下显著}}。
    NaN 不参与排序,原样返回(p_adj=NaN, reject=False)。"""
    items = sorted(((k, v) for k, v in p_values.items() if v is not None and not np.isnan(v)), key=lambda kv: kv[1])
    m = len(items)
    out = {k: {"p_adj": np.nan, "reject": False} for k in p_values}
    if m == 0:
        return out
    adj = [min(p * m / (i + 1), 1.0) for i, (_, p) in enumerate(items)]
    for i in range(m - 2, -1, -1):
        adj[i] = min(adj[i], adj[i + 1])
    k_max = -1
    for i, (_, p) in enumerate(items):
        if p <= (i + 1) / m * fdr:
            k_max = i
    for i, (k, _) in enumerate(items):
        out[k] = {"p_adj": adj[i], "reject": i <= k_max}
    return out
