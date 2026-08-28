# coding: utf-8
"""vol_20:过去 20 日对数收益标准差(低波异象候选;方向由样本内 IC 判定)。"""
import numpy as np

from factors.lib import min_periods

WINDOW = 20


def compute(ctx):
    close = ctx["close"]
    ret = np.log(close / close.shift(1))          # 缺口处 NaN,不前向填充
    return ret.rolling(WINDOW, min_periods=min_periods(WINDOW, ctx["cfg"])).std()
