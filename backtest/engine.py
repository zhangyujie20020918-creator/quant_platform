# coding: utf-8
"""最小截面回测引擎(卡2 自研侧原型;卡3 会在此基础扩红线清单)。

口径(A股真实性红线的最小子集,卡3 补全):
- T 日收盘出信号 → T+1 开盘执行(避免未来函数)
- 目标权重按总权益分配,买入用可用现金约束,逐日按收盘 mark-to-market
- 佣金 + 单边滑点(买抬价、卖压价);无价格(停牌/缺数据)的标的当日跳过
- 持有至下个调仓日;调仓=向目标权重靠拢(不在目标里的清仓)

不含(卡3 补):涨跌停不可成交、退市清算、整手约束、ST 过滤、参与率上限。
本原型只为产出可比净值,口径局限在报告里声明。
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CostModel:
    commission_rate: float = 0.0002      # 佣金双边各 万2
    slippage_rate: float = 0.0           # 单边滑点比例
    min_commission: float = 0.0          # 最低佣金(元)

    def commission(self, turnover_value):
        return max(abs(turnover_value) * self.commission_rate, self.min_commission) if turnover_value else 0.0

    def exec_price(self, price, side):
        adj = self.slippage_rate if side == "buy" else -self.slippage_rate
        return price * (1.0 + adj)


def _valid(price):
    return price is not None and not pd.isna(price) and price > 0


def run_backtest(rebalance_dates, target_weights, opens, closes, init_cash=1_000_000.0, cost=None):
    """事件循环回测。

    rebalance_dates: 信号日列表(T);target_weights: {信号日: {symbol: weight}}。
    opens/closes: DataFrame(index=交易日 datetime, columns=symbol),前复权价。
    返回 {nav, returns, trades, positions_end}。
    """
    cost = cost or CostModel()
    opens = opens.sort_index()
    closes = closes.sort_index()
    all_days = closes.index
    rebs = {pd.Timestamp(d) for d in rebalance_dates}
    tw = {pd.Timestamp(k): v for k, v in target_weights.items()}

    cash = float(init_cash)
    positions = {}                 # symbol -> shares
    pending_target = None          # 次日开盘要执行的目标权重
    nav_records, trades = [], []

    for i, day in enumerate(all_days):
        # 1) 开盘:执行昨日信号产生的调仓
        if pending_target is not None:
            cash, positions, day_trades = _rebalance(cash, positions, pending_target,
                                                      opens.loc[day], cost, day)
            trades.extend(day_trades)
            pending_target = None

        # 2) 盘后:按收盘估值
        nav = _mark_to_market(cash, positions, closes.loc[day])
        nav_records.append((day, nav))

        # 3) 若今天是调仓信号日 → 明天开盘执行(存在明天才排单)
        if day in rebs and i + 1 < len(all_days):
            pending_target = tw.get(day, {})

    nav = pd.Series(dict(nav_records)).sort_index()
    returns = nav.pct_change().fillna(0.0)
    trades_df = pd.DataFrame(trades, columns=["date", "symbol", "side", "shares", "price", "value", "cost"])
    return {"nav": nav, "returns": returns, "trades": trades_df,
            "positions_end": dict(positions)}


def _mark_to_market(cash, positions, close_row):
    value = cash
    for sym, shares in positions.items():
        px = close_row.get(sym, np.nan)
        if _valid(px):
            value += shares * px
    return value


def _rebalance(cash, positions, target_weights, open_row, cost, day):
    """把持仓向 target_weights 靠拢,按 open_row 成交。返回 (cash, positions, trades)。"""
    positions = dict(positions)
    trades = []
    equity = _mark_to_market(cash, positions, open_row)

    # ① 卖出:不在目标里的清仓(有有效价才卖)
    for sym in list(positions):
        if sym in target_weights:
            continue
        px = open_row.get(sym, np.nan)
        if not _valid(px):
            continue
        shares = positions.pop(sym)
        ep = cost.exec_price(px, "sell")
        proceeds = ep * shares
        c = cost.commission(proceeds)
        cash += proceeds - c
        trades.append({"date": day, "symbol": sym, "side": "sell", "shares": shares,
                       "price": ep, "value": proceeds, "cost": c})

    # ② 向目标金额靠拢
    for sym, w in target_weights.items():
        px = open_row.get(sym, np.nan)
        if not _valid(px):
            continue
        target_value = equity * w
        cur_shares = positions.get(sym, 0.0)
        cur_value = cur_shares * px
        diff = target_value - cur_value
        if abs(diff) < 1e-9:
            continue
        side = "buy" if diff > 0 else "sell"
        ep = cost.exec_price(px, side)
        if side == "buy":
            budget = min(diff, cash)
            if budget <= 0:
                continue
            # 含佣金约束:shares*ep*(1+comm) <= budget
            shares = budget / (ep * (1 + cost.commission_rate))
            if shares <= 0:
                continue
            value = ep * shares
            c = cost.commission(value)
            if value + c > cash + 1e-6:
                continue
            cash -= value + c
            positions[sym] = cur_shares + shares
        else:
            shares = min(-diff / ep, cur_shares)
            if shares <= 0:
                continue
            value = ep * shares
            c = cost.commission(value)
            cash += value - c
            positions[sym] = cur_shares - shares
            if positions[sym] <= 1e-9:
                positions.pop(sym)
        trades.append({"date": day, "symbol": sym, "side": side, "shares": shares,
                       "price": ep, "value": ep * shares, "cost": cost.commission(ep * shares)})

    return cash, positions, trades
