# coding: utf-8
"""DdRebound:历史高点回撤 ≥ drawdown_buy 买入、反弹至高点 × recover_sell 卖出;两周调仓;持 n_positions 只;
空位按 volume_window 日均成交额降序补;新仓各占权益 1/n,已持仓不动;退出 universe / 变 ST 的持仓清仓。
只用 ctx.panel("close")(后复权,≤asof,含当日)/ ctx.panel("amount") / ctx.holdings() / ctx.constituents / ctx.is_st,引擎无关。"""
import numpy as np

from strategies.base import CrossSectionalStrategy


class DdRebound(CrossSectionalStrategy):
    def signal(self, asof, ctx):
        p = self.params
        dd, rec = float(p["drawdown_buy"]), float(p["recover_sell"])
        n, win = int(p["n_positions"]), int(p["volume_window"])
        excl_st = bool(p.get("exclude_st", True))
        close = ctx.panel("close", asof)
        if close is None or len(close) == 0:
            return {}
        last, high = close.iloc[-1], close.max()
        ratio = last / high                                   # 现价 / 上市以来(数据起点起)最高,含当日
        cons = set(ctx.constituents(asof))

        def st(sym):
            return excl_st and ctx.is_st(sym, asof)

        keep = {}
        for sym, w in ctx.holdings().items():                 # 先卖:反弹过阈值 / 退出 universe / 变 ST
            r = ratio.get(sym, np.nan)
            if sym in cons and not np.isnan(r) and r < rec and not st(sym):
                keep[sym] = float(w)                          # 已持仓不动(目标权重 = 当前权重)
        slots = n - len(keep)
        if slots <= 0:
            return keep
        cands = [s for s in cons if s not in keep and s in ratio.index and not np.isnan(ratio[s])
                 and ratio[s] <= 1.0 - dd and close[s].notna().sum() >= 2 and not st(s)]
        if not cands:
            return keep
        avg_amt = ctx.panel("amount", asof).tail(win).mean()
        cands.sort(key=lambda s: -(float(avg_amt.get(s, np.nan)) if not np.isnan(avg_amt.get(s, np.nan)) else -1.0))
        w_new = round(1.0 / n, 12)
        for s in cands[:slots]:
            keep[s] = w_new
        return keep


def build(package):
    return DdRebound(package)
