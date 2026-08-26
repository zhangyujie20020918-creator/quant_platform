# coding: utf-8
"""玩具策略:沪深300 成分内选低波 N 只等权,月频。

**仅用于验证管道(卡2 引擎对比 / 卡7 示踪弹),不含任何研究观点。**
低波 = 过去 lookback 日对数收益的标准差;取最低 N 只等权。历史不足的标的跳过。
截面选券型原型:输入 universe(PIT)+ 复权收盘面板,输出 {调仓日: {symbol: weight}}。
"""
import numpy as np
import pandas as pd


def low_vol_weights(rebalance_dates, universe, closes, n_select=20, lookback=20):
    closes = closes.sort_index()
    out = {}
    for d in rebalance_dates:
        ts = pd.Timestamp(d)
        cons = universe.constituents(ts)
        window = closes.loc[closes.index <= ts]
        vols = {}
        for sym in cons:
            if sym not in window.columns:
                continue
            s = window[sym].dropna()
            if len(s) < lookback + 1:
                continue
            ret = np.log(s / s.shift(1)).dropna().iloc[-lookback:]
            if len(ret) < lookback:
                continue
            vols[sym] = float(ret.std())
        picked = sorted(vols, key=vols.get)[:n_select]
        w = round(1.0 / len(picked), 12) if picked else 0.0
        out[d] = {sym: w for sym in picked}
    return out
