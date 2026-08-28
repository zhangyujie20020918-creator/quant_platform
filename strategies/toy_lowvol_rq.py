# coding: utf-8
"""玩具策略 · RQAlpha 版(信号来自策略包 strategies/toy_lowvol 的 signal(),经 RQAlphaContext;口径对齐,供 SOP S4 交叉验证)。

信号:调仓日(core.calendar.rebalance_dates,默认 monthly_first)收盘后,成分(instruments.universe PIT)内每只用
history_bars(lookback+1 日收盘,前复权,跳过停牌)算对数收益标准差,取最低 n 只等权。
执行:次日集合竞价 open_auction 按开盘价"先清非目标 → 减仓 → 依剩余现金依次买入(整手)"。
- RQAlpha 日频只有 current_bar(收盘)撮合,T+1 开盘执行只能走集合竞价;集合竞价撮合**不加滑点**。
- 下单用 order_shares(数量):order_value/order_target_percent 在下单时按当前现金截断,而卖单要到撮合才回款。
**仅验证管道,不含研究观点。**
"""
import math

import numpy as np
import pandas as pd
from rqalpha.apis import get_positions, order_shares

from backtest.rqalpha_adapter.symbols import to_order_book_id
from core.calendar import TradingCalendar
from core.config import get
from instruments.cn_stock import cost_rules, dated_rate


def _valid(price):
    return price is not None and not (isinstance(price, float) and math.isnan(price)) and price > 0


def plan_rebalance(cash, positions, opens, target, costs, round_lot, date=None):
    """纯函数:开盘价下的调仓计划 → [(order_book_id, ±shares)],按提交顺序(先卖后买)。
    现金按预期回款滚动:卖出扣佣金/印花税/过户费,买入含佣金/过户费,买量按整手向下取整。"""
    comm = float(costs.get("commission_rate", 0.0))
    min_comm = float(costs.get("min_commission", 0.0))
    stamp = dated_rate(costs.get("stamp_tax_sell"), date) if date is not None else 0.0
    transfer = dated_rate(costs.get("transfer_fee"), date) if date is not None else 0.0

    def fee(value, selling):
        return max(value * comm, min_comm) + value * (transfer + (stamp if selling else 0.0))

    equity = cash + sum(q * opens[o] for o, q in positions.items() if _valid(opens.get(o)))
    expected, orders = cash, []
    # 1) 清掉不在目标里的持仓
    for obid, q in positions.items():
        if obid in target or q <= 0 or not _valid(opens.get(obid)):
            continue
        value = q * opens[obid]
        expected += value - fee(value, True)
        orders.append((obid, -q))
    # 2) 目标内超配的减仓
    buys = []
    for obid, w in target.items():
        px = opens.get(obid)
        if not _valid(px):
            continue
        q = positions.get(obid, 0)
        diff = equity * w - q * px
        if diff < 0:
            shares = min(int((-diff / px) // round_lot) * round_lot, q)
            if shares > 0:
                value = shares * px
                expected += value - fee(value, True)
                orders.append((obid, -shares))
        elif diff > 0:
            buys.append((obid, px, diff))
    # 3) 依剩余预期现金依次买入
    for obid, px, diff in buys:
        budget = min(diff, expected)
        shares = int((budget / (px * (1 + comm + transfer))) // round_lot) * round_lot
        while shares > 0 and shares * px + fee(shares * px, False) > expected:
            shares -= round_lot
        if shares <= 0:
            continue
        expected -= shares * px + fee(shares * px, False)
        orders.append((obid, shares))
    return orders


class _AdhocPackage:
    """兼容旧入口:用 params 字典临时构造一个策略包(id toy_lowvol)。"""

    def __init__(self, params):
        self.id = "toy_lowvol"
        self.config = {"id": self.id, "type": "cross_sectional", "universe": {"index": params["index"]},
                       "params": dict(params), "benchmark": [params["index"]], "risk": {}}


def make_strategy(params_or_package, cfg, root=None):
    """接受策略包(strategies.package.load_package)或旧式 params 字典;
    返回 {init, handle_bar, open_auction, state};state 是运行期记录(信号次数/每期选券),传给 run_func 前先 pop 掉。
    信号逻辑来自策略包的 signal()(RQAlphaContext),与出信号共用同一份代码。"""
    from strategies.context import RQAlphaContext, make_universe
    from strategies.package import build_strategy
    from strategies.risk import apply_risk
    from strategies.toy_lowvol.strategy import ToyLowVol

    if isinstance(params_or_package, dict):
        package = _AdhocPackage(params_or_package)
        strategy = ToyLowVol(package)
    else:
        package = params_or_package
        strategy = build_strategy(package)
    params = strategy.params
    costs = cost_rules(cfg, params.get("costs") or package.config.get("costs"))
    round_lot = int(get(cfg, "instruments.cn_stock.round_lot"))
    state = {"pending": None, "signals": 0, "picks": {}}

    def init(context):
        context.toy_universe = make_universe(package.config["universe"], cfg=cfg, root=root)   # context.universe 是 RQAlpha 保留属性
        context.toy_ctx = RQAlphaContext(context.toy_universe)
        cal = TradingCalendar.load(cfg, root=root)
        base = context.config.base
        context.reb_days = {d.date() for d in strategy.rebalance_days(cal, base.start_date, base.end_date)}
        context.toy_state = state

    def handle_bar(context, bar_dict):
        today = context.now.date()
        if today not in context.reb_days:
            return
        weights = apply_risk(strategy.signal(pd.Timestamp(today), context.toy_ctx), strategy.risk)
        state["pending"] = {to_order_book_id(sym): w for sym, w in weights.items()}
        state["signals"] += 1
        state["picks"][today] = dict(state["pending"])

    def open_auction(context, bar_dict):
        target = state["pending"]
        if target is None:
            return
        state["pending"] = None
        positions = {p.order_book_id: int(p.quantity) for p in get_positions() if p.quantity > 0}
        opens = {}
        for obid in set(positions) | set(target):
            try:
                opens[obid] = float(bar_dict[obid].last)
            except (KeyError, AttributeError, TypeError, ValueError):
                opens[obid] = float("nan")
        for obid, shares in plan_rebalance(context.portfolio.cash, positions, opens, target, costs, round_lot,
                                           date=context.now):
            order_shares(obid, shares)

    return {"init": init, "handle_bar": handle_bar, "open_auction": open_auction, "state": state}
