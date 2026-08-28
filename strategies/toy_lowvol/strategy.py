# coding: utf-8
"""ToyLowVol:策略包信号逻辑(引擎无关)。信号日 asof 用 ≤asof 的 lookback+1 个有效复权收盘算对数收益标准差,
universe(PIT)内(可选剔 ST)取最低 n_select 只等权。回测(RQAlphaContext)与出信号(StoreContext)共用。"""
import numpy as np

from strategies.base import CrossSectionalStrategy
from strategies.toy_lowvol import select_low_vol


class ToyLowVol(CrossSectionalStrategy):
    def signal(self, asof, ctx):
        p = self.params
        n, lookback, filter_st = int(p["n_select"]), int(p["lookback"]), bool(p.get("filter_st", False))
        vols = {}
        for sym in ctx.constituents(asof):
            if filter_st and ctx.is_st(sym, asof):
                continue
            closes = ctx.closes(sym, asof, lookback + 1)
            if closes is None or len(closes) < lookback + 1:
                continue
            ret = np.diff(np.log(np.asarray(closes, dtype=float)))
            vols[sym] = float(np.std(ret, ddof=1))
        return select_low_vol(vols, n)


def build(package):
    return ToyLowVol(package)
