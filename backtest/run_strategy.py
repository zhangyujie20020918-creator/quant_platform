# coding: utf-8
"""通用回测入口:任意策略包 → RQAlpha(store 数据源,品种规则表全成本)→ 报告。

用法:python -m backtest.run_strategy --strategy toy_lowvol --start 2011-06-01 --end 2022-06-30 [--date]
产出:reports/{date}_回测_<id>/backtest.md + nav.csv + rq_runs/(RQAlpha 完整报表,面板可读)。
交叉验证专用入口仍是 backtest.run_rqalpha_toy(带自研对照);本入口是"给别人用"的傻瓜版。
"""
from core.bootstrap import init  # noqa: F401  必须第一行

import argparse
import datetime as dt
import os
import time
import warnings

import pandas as pd
from rqalpha import run_func

from backtest.metrics import nav_stats
from backtest.rqalpha_adapter.symbols import to_order_book_id
from core.config import ROOT, load_config
from core.outputs import report_dir, run_dir
from strategies.context import make_universe
from strategies.package import build_strategy, load_package
from strategies.toy_lowvol_rq import make_strategy

warnings.filterwarnings("ignore", category=FutureWarning, module="rqalpha")


def run_strategy(strategy_id, cfg, start, end, root=None, packages_root=None, config_path=None, date=None,
                 init_cash=1_000_000.0):
    root = root or ROOT
    date = date or dt.date.today().isoformat()
    pkg = load_package(strategy_id, root=packages_root)
    strategy = build_strategy(pkg)
    preload = make_universe(pkg.config["universe"], cfg=cfg, root=root).all_symbols()
    benchmark = to_order_book_id(strategy.benchmark[0])
    out_dir = report_dir("回测_" + strategy_id, date=date, cfg=cfg, root=root)
    rq_dir = run_dir("回测_" + strategy_id, "rq", date=date, cfg=cfg, root=root)

    funcs = make_strategy(pkg, cfg=cfg, root=root)
    state = funcs.pop("state")
    mod_store = {"enabled": True, "lib": "backtest.rqalpha_adapter.mod", "preload": preload, "root": root}
    if config_path:
        mod_store["config_path"] = config_path
    config = {
        "base": {"start_date": start, "end_date": end, "accounts": {"stock": init_cash},
                 "data_bundle_path": os.path.join(root, "no_bundle")},
        "extra": {"log_level": "error"},
        "mod": {"store": mod_store, "sys_progress": {"enabled": False},
                "sys_analyser": {"enabled": True, "plot": False, "benchmark": benchmark, "report_save_path": rq_dir}},
    }
    t0 = time.time()
    res = run_func(config=config, **funcs)["sys_analyser"]
    nav = res["portfolio"]["total_value"].copy()
    nav.index = pd.to_datetime(nav.index).normalize()
    bench = res["benchmark_portfolio"]["unit_net_value"].copy() * init_cash
    bench.index = pd.to_datetime(bench.index).normalize()
    stats, bstats = nav_stats(nav), nav_stats(bench)
    navs = pd.DataFrame({"strategy": nav, "benchmark": bench})
    navs.index.name = "date"
    navs.to_csv(os.path.join(out_dir, "nav.csv"), encoding="utf-8-sig")
    s = res["summary"]
    lines = [
        "# 回测报告 · %s(%s)" % (strategy_id, pkg.config["name"]), "",
        "区间 %s → %s;初始资金 %.0f;universe %s;基准 %s;状态 **%s**。" % (start, end, init_cash, pkg.config["universe"],
                                                                     strategy.benchmark[0], pkg.config["status"]),
        "参数:%s;风控:%s;成本:品种规则表 instruments.cn_stock.costs;RQAlpha 内置涨跌停/停牌/T+1/退市清算。"
        % (strategy.params, strategy.risk), "",
        "| | 总收益 | 年化 | 最大回撤 | 夏普 |", "|---|---|---|---|---|",
        "| 策略 | %.1f%% | %.2f%% | %.1f%% | %.2f |" % (stats["total_return"] * 100, stats["cagr"] * 100, stats["max_drawdown"] * 100, stats["sharpe"]),
        "| 基准 | %.1f%% | %.2f%% | %.1f%% | %.2f |" % (bstats["total_return"] * 100, bstats["cagr"] * 100, bstats["max_drawdown"] * 100, bstats["sharpe"]),
        "",
        "- 信号 %d 次,成交 %d 笔;RQAlpha summary:alpha %s / beta %s / 信息比率 %s;耗时 %.0fs。"
        % (state["signals"], len(res["trades"]), s.get("alpha"), s.get("beta"), s.get("information_ratio"), time.time() - t0),
        "- 产出:`nav.csv`、`rq_runs/`(portfolio/trades/positions/summary,面板「回测浏览器」可看)。",
        "- 局限:集合竞价撮合无滑点;结论仅对该 universe 有效;策略状态非 approved 时不构成任何投资依据。", "",
    ]
    path = os.path.join(out_dir, "backtest.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return {"report": path, "nav": navs, "stats": stats, "benchmark_stats": bstats, "trades": len(res["trades"]),
            "signals": state["signals"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--start", default="2011-06-01")
    ap.add_argument("--end", default="2022-06-30")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--cash", type=float, default=1_000_000.0)
    args = ap.parse_args()
    log = init("run_strategy")
    out = run_strategy(args.strategy, load_config(), args.start, args.end, date=args.date, init_cash=args.cash)
    st = out["stats"]
    log.info("%s:总收益 %.1f%% | 年化 %.2f%% | 回撤 %.1f%% | 夏普 %.2f | %d 笔 → %s",
             args.strategy, st["total_return"] * 100, st["cagr"] * 100, st["max_drawdown"] * 100, st["sharpe"], out["trades"], out["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
