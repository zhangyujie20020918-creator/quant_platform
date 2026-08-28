# coding: utf-8
"""参数平原扫描(SOP S3:敏感性扫描呈现平原/悬崖,悬崖参数不用):对策略包的两个参数做网格,每格一次完整回测。

用法:python -m backtest.run_sensitivity --strategy dd_rebound --start 2019-01-01 --end 2025-12-30 --cash 100000
      --grid "params.drawdown_buy=0.70,0.75,0.80" --grid "params.recover_sell=0.40,0.50,0.60" [--date]
产出:reports/{date}_回测_<id>/sensitivity.md(年化 / 回撤 / 夏普 三张九宫格 + 悬崖判定)。
"""
from core.bootstrap import init  # noqa: F401  必须第一行

import argparse
import datetime as dt
import itertools
import os
import time

from backtest.run_strategy import run_strategy
from core.config import get, load_config
from core.outputs import report_dir


def parse_grid(spec):
    path, values = spec.split("=", 1)
    return path.strip(), [float(v) for v in values.split(",")]


def cliff(cells, threshold_ratio, axes=None):
    """相邻格(网格上每个维度索引相差 ≤1 且只有一个维度不同)年化差 > threshold_ratio × max(|两格年化|) 即视为悬崖;
    axes: 各维度的取值列表(定义"相邻");缺省时按各维度出现过的取值排序推断。返回 [(a, b, cagr_a, cagr_b)]。"""
    keys = list(cells)
    if not keys:
        return []
    ndim = len(keys[0])
    axes = axes or [sorted({k[i] for k in keys}) for i in range(ndim)]
    pos = {k: tuple(axes[i].index(k[i]) for i in range(ndim)) for k in keys}
    out = []
    for a in keys:
        for b in keys:
            if a >= b:
                continue
            d = [abs(pos[a][i] - pos[b][i]) for i in range(ndim)]
            if sum(1 for x in d if x) == 1 and max(d) == 1:            # 恰好一个维度相邻一格
                ra, rb = cells[a]["cagr"], cells[b]["cagr"]
                scale = max(abs(ra), abs(rb), 1e-9)
                if abs(ra - rb) > threshold_ratio * scale:
                    out.append((a, b, ra, rb))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--cash", type=float, default=1_000_000.0)
    ap.add_argument("--grid", action="append", required=True, help='如 "params.drawdown_buy=0.70,0.75,0.80"')
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--cliff-ratio", type=float, default=None, help="悬崖判定比例(默认读 config protocol.plateau_cliff_ratio)")
    ap.add_argument("--rebuild", action="store_true", help="不重跑,从已有各格 nav.csv 重建九宫格与悬崖判定")
    args = ap.parse_args()
    log = init("sensitivity")
    cfg = load_config()
    ratio = args.cliff_ratio if args.cliff_ratio is not None else float(get(cfg, "protocol.plateau_cliff_ratio"))
    grids = [parse_grid(g) for g in args.grid]
    names = [g[0] for g in grids]
    cells = {}
    t0 = time.time()
    for combo in itertools.product(*[g[1] for g in grids]):
        overrides = dict(zip(names, combo))
        tag = "_".join("%s%g" % (n.split(".")[-1], v) for n, v in overrides.items())
        log.info("▶ %s", overrides)
        if args.rebuild:
            import pandas as pd
            from backtest.metrics import nav_stats
            from core.config import ROOT
            d = os.path.join(ROOT, "reports", "%s_回测_%s_sens_%s" % (args.date, args.strategy, tag))
            nav = pd.read_csv(os.path.join(d, "nav.csv"), parse_dates=["date"]).set_index("date")["strategy"]
            trades = pd.read_csv(os.path.join(d, "rq_runs", "trades.csv"), encoding="utf-8-sig")
            out = {"stats": nav_stats(nav), "trades": len(trades)}
        else:
            out = run_strategy(args.strategy, cfg, args.start, args.end, date=args.date, init_cash=args.cash,
                               overrides=overrides, tag="sens_" + tag)
        cells[combo] = dict(out["stats"], trades=out["trades"])
        log.info("   年化 %.2f%% 回撤 %.1f%% 夏普 %.2f(%d 笔)", out["stats"]["cagr"] * 100, out["stats"]["max_drawdown"] * 100,
                 out["stats"]["sharpe"], out["trades"])
    cliffs = cliff(cells, ratio, axes=[g[1] for g in grids])

    rows, cols = grids[0][1], (grids[1][1] if len(grids) > 1 else [None])
    lines = ["# 参数平原扫描 · %s(%s → %s,本金 %.0f)" % (args.strategy, args.start, args.end, args.cash), "",
             "网格:%s;每格一次完整回测(同一策略包,只覆盖被扫描的参数);悬崖判定:相邻格年化差 > %.0f%% × 两格年化绝对值的较大者(config protocol.plateau_cliff_ratio)。"
             % ("; ".join("%s ∈ {%s}" % (n, ", ".join("%g" % v for v in g[1])) for n, g in zip(names, grids)), ratio * 100), ""]
    for metric, title, scale, fmt in (("cagr", "年化(%)", 100, "%.2f"), ("max_drawdown", "最大回撤(%)", 100, "%.1f"),
                                       ("sharpe", "夏普", 1, "%.2f"), ("trades", "成交笔数", 1, "%d")):
        scaled = {k: {metric: (v[metric] * scale if metric != "trades" else v[metric])} for k, v in cells.items()}
        lines += ["## " + title, ""]
        lines += ["| %s \\ %s | " % (names[0], names[1] if len(grids) > 1 else "") + " | ".join("%g" % c for c in cols) + " |",
                  "|---|" + "---|" * len(cols)]
        for r in rows:
            vals = []
            for c in cols:
                key = (r, c) if c is not None else (r,)
                vals.append((fmt % scaled[key][metric]) if key in scaled else "—")
            lines += ["| %g | " % r + " | ".join(vals) + " |"]
        lines += [""]
    lines += ["## 平原/悬崖判定", ""]
    if cliffs:
        lines += ["**存在悬崖 %d 处**(悬崖参数不用):" % len(cliffs)] + \
                 ["- %s vs %s:年化 %.2f%% → %.2f%%" % (a, b, ra * 100, rb * 100) for a, b, ra, rb in cliffs]
    else:
        lines += ["**未发现悬崖**:相邻格年化差均在阈内,参数区域为平原。"]
    lines += ["", "- 耗时 %.0f 分钟;各格完整报表在 `reports/%s_回测_%s_sens_*/`。" % ((time.time() - t0) / 60, args.date, args.strategy), ""]
    path = os.path.join(report_dir("回测_" + args.strategy, date=args.date), "sensitivity.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("报告:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
