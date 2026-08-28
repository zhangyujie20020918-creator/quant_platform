# coding: utf-8
"""信号文件契约 orders_{signal_date}.csv(SOP S5;未来执行服务的输入,schema 从第一天按可直接消费设计)。

语义:文件 = 该策略的**完整目标组合**,未列出的标的目标权重为 0;side 固定 long(本平台只做多);
target_weight ∈ [0,1] 且合计 ≤ 1(差额留现金);ref_price = 信号日原始收盘(执行参考,非成交价);
data_asof = 数据末日,data_lag_days = 数据落后交易日数(新鲜度)。
"""
import re

import numpy as np
import pandas as pd

COLUMNS = ["strategy_id", "signal_date", "symbol", "side", "target_weight", "ref_price",
           "data_asof", "data_lag_days", "generated_at"]
SIDES = ("long",)
_SYMBOL = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")


class SignalError(ValueError):
    pass


def validate_orders(df, tol=1e-9):
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise SignalError("信号文件缺列: %s" % ", ".join(missing))
    if df["symbol"].duplicated().any():
        raise SignalError("信号文件有重复标的: %s" % df.loc[df["symbol"].duplicated(), "symbol"].tolist())
    bad_sym = [s for s in df["symbol"] if not _SYMBOL.match(str(s))]
    if bad_sym:
        raise SignalError("symbol 不合平台口径(600000.SH): %s" % bad_sym)
    if not df["side"].isin(SIDES).all():
        raise SignalError("side 只允许 %s" % "/".join(SIDES))
    w = pd.to_numeric(df["target_weight"], errors="coerce")
    if w.isna().any() or (w < 0).any() or (w > 1 + tol).any():
        raise SignalError("target_weight 须在 [0, 1]")
    if w.sum() > 1 + tol:
        raise SignalError("target_weight 合计 %.4f > 1" % w.sum())
    px = pd.to_numeric(df["ref_price"], errors="coerce")
    if px.isna().any() or (px <= 0).any():
        raise SignalError("ref_price 须为正数")
    lag = pd.to_numeric(df["data_lag_days"], errors="coerce")
    if lag.isna().any() or (lag < 0).any() or not np.allclose(lag, lag.round()):
        raise SignalError("data_lag_days 须为非负整数")
    if df["strategy_id"].nunique() != 1 or df["signal_date"].nunique() != 1:
        raise SignalError("一份信号文件只能属于一个策略、一个信号日")
    return True
