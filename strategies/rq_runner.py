# coding: utf-8
"""RQAlpha 胶水(通用):任意策略包 → run_func 所需的 init / handle_bar / open_auction。

信号:调仓日(策略包 params.rebalance,走 core.calendar)收盘后 strategy.signal(asof, RQAlphaContext) → 目标权重 → apply_risk。
执行(策略包 execution.mode):
  next_open  —— 次日集合竞价按开盘价成交(RQAlpha 集合竞价撮合**不加滑点**);
  next_close —— 次日 handle_bar 按收盘价成交,sys_simulation 的滑点(execution.slippage)生效。
两种模式都是"先清非目标 → 减仓 → 依剩余现金依次买入(整手)"(plan_rebalance 纯函数,计入佣金/税费/滑点)。
下单用 order_shares(数量):order_value/order_target_percent 在下单时按当前现金截断,而卖单要到撮合才回款。
"""
import math

import pandas as pd
from rqalpha.apis import get_positions, order_shares

from backtest.rqalpha_adapter.symbols import to_order_book_id
from core.calendar import TradingCalendar
from core.config import get
from instruments.cn_stock import cost_rules, dated_rate
from strategies.context import RQAlphaContext, StoreContext, make_universe
from strategies.package import build_strategy
from strategies.risk import apply_risk

PANEL_BUFFER_CAL_DAYS = 400     # 面板起点提前的自然日数(机制常量;历史高点类策略会用到全历史,面板从数据起点起)


def _valid(price):
    return price is not None and not (isinstance(price, float) and math.isnan(price)) and price > 0


def plan_rebalance(cash, positions, prices, target, costs, round_lot, date=None, slippage=0.0):
    """纯函数:按当前价的调仓计划 → [(order_book_id, ±shares)],先卖后买。
    现金按预期回款滚动:卖出按 price×(1−滑点) 扣佣金/印花税/过户费,买入按 price×(1+滑点) 含佣金/过户费,买量整手向下取整。"""
    comm = float(costs.get("commission_rate", 0.0))
    min_comm = float(costs.get("min_commission", 0.0))
    stamp = dated_rate(costs.get("stamp_tax_sell"), date) if date is not None else 0.0
    transfer = dated_rate(costs.get("transfer_fee"), date) if date is not None else 0.0
    slip = float(slippage or 0.0)

    def fee(value, selling):
        return max(value * comm, min_comm) + value * (transfer + (stamp if selling else 0.0))

    equity = cash + sum(q * prices[o] for o, q in positions.items() if _valid(prices.get(o)))
    expected, orders = cash, []
    for obid, q in positions.items():                                  # 1) 清掉不在目标里的持仓
        if obid in target or q <= 0 or not _valid(prices.get(obid)):
            continue
        value = q * prices[obid] * (1 - slip)
        expected += value - fee(value, True)
        orders.append((obid, -q))
    buys = []
    for obid, w in target.items():                                     # 2) 目标内超配的减仓
        px = prices.get(obid)
        if not _valid(px):
            continue
        q = positions.get(obid, 0)
        diff = equity * w - q * px
        if diff < 0:
            shares = min(int((-diff / px) // round_lot) * round_lot, q)
            if shares > 0:
                value = shares * px * (1 - slip)
                expected += value - fee(value, True)
                orders.append((obid, -shares))
        elif diff > 0:
            buys.append((obid, px, diff))
    for obid, px, diff in buys:                                        # 3) 依剩余预期现金依次买入
        budget = min(diff, expected)
        px_buy = px * (1 + slip)
        shares = int((budget / (px_buy * (1 + comm + transfer))) // round_lot) * round_lot
        while shares > 0 and shares * px_buy + fee(shares * px_buy, False) > expected:
            shares -= round_lot
        if shares <= 0:
            continue
        expected -= shares * px_buy + fee(shares * px_buy, False)
        orders.append((obid, shares))
    return orders


class _AdhocPackage:
    """兼容旧入口:用 params 字典临时构造一个策略包(id toy_lowvol)。"""

    def __init__(self, params):
        self.id = "toy_lowvol"
        self.config = {"id": self.id, "type": "cross_sectional", "universe": {"index": params["index"]},
                       "params": dict(params), "benchmark": [params["index"]], "risk": {},
                       "execution": {"mode": "next_open", "slippage": 0.0}}


def make_strategy(params_or_package, cfg, root=None):
    """接受策略包(strategies.package.load_package)或旧式 params 字典;返回 {init, handle_bar, open_auction, state};
    state 是运行期记录(信号次数 / 每期选券 / 每期持仓),传给 run_func 前先 pop 掉。"""
    if isinstance(params_or_package, dict):
        from strategies.toy_lowvol.strategy import ToyLowVol
        package = _AdhocPackage(params_or_package)
        strategy = ToyLowVol(package)
    else:
        package = params_or_package
        strategy = build_strategy(package)
    params = strategy.params
    execution = dict(package.config.get("execution") or {"mode": "next_open", "slippage": 0.0})
    mode, slippage = execution.get("mode", "next_open"), float(execution.get("slippage", 0.0) or 0.0)
    costs = cost_rules(cfg, params.get("costs") or package.config.get("costs"))
    round_lot = int(get(cfg, "instruments.cn_stock.round_lot"))
    state = {"pending": None, "signals": 0, "picks": {}, "holdings_seen": {}, "mode": mode}

    def init(context):
        universe = make_universe(package.config["universe"], cfg=cfg, root=root)
        base = context.config.base
        start = (pd.Timestamp(base.start_date) - pd.Timedelta(days=PANEL_BUFFER_CAL_DAYS)).strftime("%Y-%m-%d")
        # 面板懒加载:只有调用 ctx.panel() 的策略才会读整段 store 面板(从数据起点起,历史高点类策略需要全历史)
        context.toy_ctx = RQAlphaContext(universe, panel_loader=lambda: StoreContext.load(
            cfg, root, package.config["universe"], "1900-01-01", pd.Timestamp(base.end_date)))
        cal = TradingCalendar.load(cfg, root=root)
        context.reb_days = {d.date() for d in strategy.rebalance_days(cal, base.start_date, base.end_date)}
        context.toy_state = state
        context.panel_start = start

    def _execute(context, bar_dict, price_field):
        target = state["pending"]
        state["pending"] = None
        positions = {p.order_book_id: int(p.quantity) for p in get_positions() if p.quantity > 0}
        prices = {}
        for obid in set(positions) | set(target):
            try:
                prices[obid] = float(getattr(bar_dict[obid], price_field))
            except (KeyError, AttributeError, TypeError, ValueError):
                prices[obid] = float("nan")
        for obid, shares in plan_rebalance(context.portfolio.cash, positions, prices, target, costs, round_lot,
                                           date=context.now, slippage=slippage):
            order_shares(obid, shares)

    def handle_bar(context, bar_dict):
        today = context.now.date()
        if mode == "next_close" and state["pending"] is not None:      # 先执行昨日信号(次日收盘,滑点生效)
            _execute(context, bar_dict, "close")
        if today not in context.reb_days:
            return
        state["holdings_seen"][today] = context.toy_ctx.holdings()
        weights = apply_risk(strategy.signal(pd.Timestamp(today), context.toy_ctx), strategy.risk)
        state["pending"] = {to_order_book_id(sym): w for sym, w in weights.items()}
        state["signals"] += 1
        state["picks"][today] = dict(state["pending"])

    def open_auction(context, bar_dict):
        if mode == "next_open" and state["pending"] is not None:
            _execute(context, bar_dict, "last")

    return {"init": init, "handle_bar": handle_bar, "open_auction": open_auction, "state": state}
