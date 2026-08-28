# coding: utf-8
"""rev_20:过去 20 日收益 close_t / close_{t-20} − 1(A股短期反转,阳性对照;lower_better)。"""
WINDOW = 20


def compute(ctx):
    close = ctx["close"]
    return close / close.shift(WINDOW) - 1
