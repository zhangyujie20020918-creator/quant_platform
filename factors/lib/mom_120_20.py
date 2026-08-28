# coding: utf-8
"""mom_120_20:跳过最近 20 日的中期动量 close_{t-20} / close_{t-120} − 1(12-1 动量的日频近似;higher_better)。"""
SKIP, WINDOW = 20, 120


def compute(ctx):
    close = ctx["close"]
    return close.shift(SKIP) / close.shift(WINDOW) - 1
