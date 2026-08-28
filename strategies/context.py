# coding: utf-8
"""SignalContext 两个实现:StoreContext(出信号:store 面板)/ RQAlphaContext(回测:RQAlpha API + 懒加载的 store 面板)。

接口(都用平台 symbol 口径 600000.SH):
  constituents(asof) / is_st(symbol, asof) / closes(symbol, asof, n)
  panel(name, asof)  → ≤asof 的 DataFrame(date × symbol):"close" 后复权收盘、"amount" 原始成交额(向量化算高点/均额)
  holdings()         → {symbol: 当前权重}(回测来自 RQAlpha 持仓;出信号来自上一份信号文件,或空)
"""
import pandas as pd

from backtest.prices import adjusted_panels
from backtest.rqalpha_adapter.stores import StoreSTDateSet
from backtest.rqalpha_adapter.symbols import to_order_book_id, to_symbol
from data import store
from instruments.universe import BoardUniverse, IndexUniverse


class FixedUniverse:
    """时序配置原型的固定资产清单。"""

    def __init__(self, symbols):
        self._symbols = list(symbols)

    def constituents(self, asof):
        return list(self._symbols)

    def all_symbols(self):
        return list(self._symbols)


def make_universe(spec, cfg=None, root=None):
    """策略包 universe 小节:{"index": "000300.SH"} → 指数成分 PIT;{"boards": [...]} → 板块全市场 PIT;
    {"symbols": [...]} → 固定清单。"""
    if "index" in spec:
        return IndexUniverse(spec["index"], root=root, cfg=cfg)
    if "boards" in spec:
        return BoardUniverse(spec["boards"], root=root, cfg=cfg)
    if "symbols" in spec:
        return FixedUniverse(spec["symbols"])
    raise ValueError("universe 须含 index / boards / symbols 之一: %r" % (spec,))


class StoreContext:
    def __init__(self, universe, closes, st, amount=None, holdings=None):
        self._uni, self._closes, self._st = universe, closes, st
        self._panels = {"close": closes}
        if amount is not None:
            self._panels["amount"] = amount
        self._holdings = dict(holdings or {})

    @classmethod
    def load(cls, cfg, root, universe_spec, start, end, holdings=None):
        uni = make_universe(universe_spec, cfg=cfg, root=root)
        symbols = uni.all_symbols()
        (closes,) = adjusted_panels(symbols, start, end, root=root, cfg=cfg, method="hfq", fields=("close",))
        raw = store.read_table("stock_daily", start=start, end=end, symbols=symbols, columns=["date", "symbol", "amount"],
                               root=root, cfg=cfg)
        amount = raw.pivot(index="date", columns="symbol", values="amount").reindex(columns=symbols).sort_index() if len(raw) else None
        if amount is not None:
            amount.index = pd.to_datetime(amount.index)
        return cls(uni, closes, StoreSTDateSet.load(cfg, root), amount=amount, holdings=holdings)

    def constituents(self, asof):
        return self._uni.constituents(pd.Timestamp(asof))

    def is_st(self, symbol, asof):
        return bool(self._st.flags(symbol, pd.DatetimeIndex([pd.Timestamp(asof)]))[0])

    def closes(self, symbol, asof, n):
        if symbol not in self._closes.columns:
            return None
        s = self._closes[symbol].loc[:pd.Timestamp(asof)].dropna()
        return s.tail(int(n)).to_numpy(dtype=float) if len(s) else None

    def panel(self, name, asof):
        p = self._panels.get(name)
        if p is None:
            raise KeyError("StoreContext 没有面板 %r(可用: %s)" % (name, ", ".join(self._panels)))
        return p.loc[:pd.Timestamp(asof)]

    def holdings(self):
        return dict(self._holdings)


class RQAlphaContext:
    """回测用:价格/ST 走 RQAlpha API(与撮合同一份数据);面板懒加载 StoreContext(同一 store,只暴露 ≤asof);
    持仓来自 RQAlpha 组合。"""

    def __init__(self, universe, panel_loader=None):
        self._uni, self._loader, self._store_ctx = universe, panel_loader, None

    def constituents(self, asof):
        return self._uni.constituents(pd.Timestamp(asof))

    def is_st(self, symbol, asof):
        from rqalpha.apis import instruments, is_st_stock
        obid = to_order_book_id(symbol)
        return instruments(obid) is not None and bool(is_st_stock(obid))

    def closes(self, symbol, asof, n):
        from rqalpha.apis import history_bars, instruments
        obid = to_order_book_id(symbol)
        if instruments(obid) is None:
            return None
        bars = history_bars(obid, int(n), "1d", "close")
        return None if bars is None else bars

    def panel(self, name, asof):
        if self._store_ctx is None:
            if self._loader is None:
                raise RuntimeError("RQAlphaContext 未配置面板加载器")
            self._store_ctx = self._loader()
        return self._store_ctx.panel(name, asof)

    def holdings(self):
        from rqalpha.apis import get_positions
        from rqalpha.environment import Environment
        total = float(Environment.get_instance().portfolio.total_value)
        if total <= 0:
            return {}
        return {to_symbol(p.order_book_id): float(p.market_value) / total for p in get_positions() if p.quantity > 0}
