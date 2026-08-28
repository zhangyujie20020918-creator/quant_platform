# coding: utf-8
"""SignalContext 两个实现:StoreContext(出信号:store 面板)/ RQAlphaContext(回测:RQAlpha API)。
接口:constituents(asof) / is_st(symbol, asof) / closes(symbol, asof, n) —— 都用平台 symbol 口径(600000.SH)。"""
import pandas as pd

from backtest.prices import adjusted_panels
from backtest.rqalpha_adapter.stores import StoreSTDateSet
from backtest.rqalpha_adapter.symbols import to_order_book_id
from instruments.universe import IndexUniverse


class FixedUniverse:
    """时序配置原型的固定资产清单。"""

    def __init__(self, symbols):
        self._symbols = list(symbols)

    def constituents(self, asof):
        return list(self._symbols)

    def all_symbols(self):
        return list(self._symbols)


def make_universe(spec, cfg=None, root=None):
    """策略包 universe 小节:{"index": "000300.SH"} → IndexUniverse(PIT);{"symbols": [...]} → FixedUniverse。"""
    if "index" in spec:
        return IndexUniverse(spec["index"], root=root, cfg=cfg)
    if "symbols" in spec:
        return FixedUniverse(spec["symbols"])
    raise ValueError("universe 须含 index 或 symbols: %r" % (spec,))


class StoreContext:
    def __init__(self, universe, closes, st):
        self._uni, self._closes, self._st = universe, closes, st

    @classmethod
    def load(cls, cfg, root, universe_spec, start, end):
        uni = make_universe(universe_spec, cfg=cfg, root=root)
        symbols = uni.all_symbols()
        (closes,) = adjusted_panels(symbols, start, end, root=root, cfg=cfg, method="hfq", fields=("close",))
        return cls(uni, closes, StoreSTDateSet.load(cfg, root))

    def constituents(self, asof):
        return self._uni.constituents(pd.Timestamp(asof))

    def is_st(self, symbol, asof):
        return bool(self._st.flags(symbol, pd.DatetimeIndex([pd.Timestamp(asof)]))[0])

    def closes(self, symbol, asof, n):
        if symbol not in self._closes.columns:
            return None
        s = self._closes[symbol].loc[:pd.Timestamp(asof)].dropna()
        return s.tail(int(n)).to_numpy(dtype=float) if len(s) else None


class RQAlphaContext:
    def __init__(self, universe):
        self._uni = universe

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
