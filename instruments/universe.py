# coding: utf-8
"""指数成分 universe(PIT):instruments 层,strategy/factors 都依赖它。

架构要点(旧项目 factors⇄strategy 循环之债的根治):候选池/universe 逻辑住在独立的
instruments 层,不住 strategy——signals 与 strategies 都可依赖 universe,universe 不反依赖它们。

PIT 纪律:as-of 日 d 的成分 = index_weight 中日期 ≤ d 的最近一次快照(避免用到未来调仓)。
"""
import numpy as np
import pandas as pd

from data import store


def index_constituents(index_symbol, asof, root=None, cfg=None):
    """as-of 日的成分列表(最近 ≤ asof 的快照);无则空列表。"""
    return IndexUniverse(index_symbol, root=root, cfg=cfg).constituents(asof)


class IndexUniverse:
    """一个指数的历史成分,加载一次、多日查询。"""

    def __init__(self, index_symbol, root=None, cfg=None):
        self.index_symbol = index_symbol
        w = store.read_table("index_weight", root=root, cfg=cfg)
        self._w = w[w["index_symbol"] == index_symbol].copy() if len(w) else w
        if len(self._w):
            self._w["date"] = pd.to_datetime(self._w["date"])
            self._snap_dates = self._w["date"].drop_duplicates().sort_values()
        else:
            self._snap_dates = pd.DatetimeIndex([])

    def constituents(self, asof):
        asof = pd.Timestamp(asof)
        valid = self._snap_dates[self._snap_dates <= asof]
        if len(valid) == 0:
            return []
        snap = valid.max()
        rows = self._w[self._w["date"] == snap]
        return sorted(rows["symbol"].tolist())

    def all_symbols(self):
        """历史上出现过的全部成分(建全历史价格面板时用)。"""
        return sorted(self._w["symbol"].unique().tolist()) if len(self._w) else []


class BoardUniverse:
    """按板块的全市场股票池(PIT):stock_basic.market ∈ boards,上市日 ≤ asof < 退市日;含已退市股,防幸存者偏差。
    ST 剔除不在此层(由策略经 ctx.is_st 按日判断)。"""

    def __init__(self, boards, root=None, cfg=None):
        b = store.read_table("stock_basic", root=root, cfg=cfg)
        b = b[b["market"].isin(list(boards))].sort_values("symbol") if len(b) else b
        self.boards = list(boards)
        self._symbols = b["symbol"].tolist()
        self._list = pd.to_datetime(b["list_date"]).to_numpy()
        self._delist = pd.to_datetime(b["delist_date"]).to_numpy()

    def constituents(self, asof):
        ts = np.datetime64(pd.Timestamp(asof))
        listed = self._list <= ts
        alive = pd.isna(self._delist) | (self._delist > ts)
        return [s for s, ok in zip(self._symbols, listed & alive) if ok]

    def all_symbols(self):
        return list(self._symbols)
