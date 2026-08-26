# coding: utf-8
"""复权价格面板:从 store 读 stock_daily(原始)+ adj_factor,输出 date×symbol 的复权面板。

- hfq(后复权,默认)= 原始价 × adj_factor:单调、无未来重基,回测首选。
- qfq(前复权)= 原始价 × adj_factor / 该股最新 adj_factor:贴近当前价,便于人读。
无复权因子的行按因子=1 处理(用原始价,声明局限)。
这是引擎/策略接真实数据的唯一价格入口(前复权红线的落点)。
"""
import pandas as pd

from data import store

_PRICE_COLS = ("open", "high", "low", "close", "pre_close")


def adjusted_panels(symbols, start, end, root=None, cfg=None, method="hfq", fields=("open", "close")):
    """返回 tuple(按 fields 顺序)的 date×symbol 复权面板。默认 (opens, closes)。"""
    daily = store.read_table("stock_daily", start=start, end=end, symbols=symbols, root=root, cfg=cfg)
    adj = store.read_table("adj_factor", start=start, end=end, symbols=symbols, root=root, cfg=cfg)

    if daily.empty:
        empty = pd.DataFrame(columns=list(symbols))
        return tuple(empty.copy() for _ in fields)

    df = daily.merge(adj[["date", "symbol", "adj_factor"]], on=["date", "symbol"], how="left")
    df["adj_factor"] = df["adj_factor"].fillna(1.0)

    if method == "qfq":
        latest = df.sort_values("date").groupby("symbol")["adj_factor"].transform("last")
        factor = df["adj_factor"] / latest
    elif method == "hfq":
        factor = df["adj_factor"]
    else:
        raise ValueError("未知复权方式: %r(hfq/qfq)" % method)

    out = []
    for f in fields:
        df["_adj"] = df[f] * factor
        panel = df.pivot(index="date", columns="symbol", values="_adj").reindex(columns=list(symbols))
        panel.index = pd.to_datetime(panel.index)
        out.append(panel.sort_index())
    return tuple(out)
