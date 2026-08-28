# coding: utf-8
"""玩具策略包:沪深300 成分内选低波 N 只等权,月频(卡5 起为策略包;卡2/卡3 的面板版函数保留在此供自研引擎交叉验证)。

**仅用于验证管道(卡2 引擎对比 / 卡3 交叉验证 / 卡5 信号契约 / 卡7 示踪弹),不含任何研究观点。**
低波 = 过去 lookback 日对数收益的标准差;取最低 N 只等权。历史不足的标的跳过。
- select_low_vol:唯一选券函数(自研引擎、RQAlpha 版、策略包 signal 共用)。
- low_vol_weights:面板版(自研 backtest.engine 用),输入 universe(PIT)+ 复权收盘面板,输出 {调仓日: {symbol: weight}}。
- strategy.py:ToyLowVol(CrossSectionalStrategy)= 策略包信号逻辑。
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
        out[d] = select_low_vol(vols, n_select)
    return out


def select_low_vol(vols, n_select):
    """{symbol: 波动} → 取最低 n 只等权 {symbol: weight}(自研引擎与 RQAlpha 版共用的唯一选券逻辑)。"""
    picked = sorted(vols, key=vols.get)[:n_select]
    w = round(1.0 / len(picked), 12) if picked else 0.0
    return {sym: w for sym in picked}
