# coding: utf-8
"""前瞻收益(T+1 口径锁死,全平台唯一入口;自 cb_quant 平移)。

信号日 T 用 T 收盘算出因子;收益 = open[T+1+H] / open[T+1] − 1:T+1 开盘买入、持有 H 个交易日、
T+1+H 开盘卖出——与回测执行口径(信号收盘、次日开盘)完全一致。**任何用 close[T] 起算的"前瞻收益"
都把当日收盘信息算进了收益,视为违规。**
买入价/卖出价 ≤0 或缺失(停牌/缺数据)→ NaN,不能让 0 做分母出 inf 污染均值类统计。
"""
import numpy as np


def forward_returns(open_panel, holding_days):
    """open_panel: DataFrame(date × symbol) 开盘价(复权口径需一致)。返回同形 DataFrame,index=信号日 T。
    靠近数据末尾拿不到 T+1+H 的行为 NaN,是正常现象,IC 对齐时随 dropna 消失。"""
    if holding_days < 1:
        raise ValueError("holding_days 必须 ≥ 1")
    buy = open_panel.shift(-1)
    sell = open_panel.shift(-1 - holding_days)
    invalid = (buy <= 0) | (sell <= 0) | buy.isna() | sell.isna()
    return (sell / buy - 1).mask(invalid, np.nan)
