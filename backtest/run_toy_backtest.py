# coding: utf-8
"""玩具策略真实数据回测运行器(卡2 自研侧收官 / 卡7 示踪弹雏形)。

串起:instruments.universe(沪深300 PIT)+ backtest.prices(后复权面板)+
strategies.toy_lowvol(低波N选)+ backtest.engine(截面事件循环)→ 净值 + 基准对比。

用法:python -m backtest.run_toy_backtest --start 2011-06-01 --end 2022-06-30
"""
import argparse
import datetime as _dt
import os

import numpy as np
import pandas as pd

from backtest.engine import CostModel, run_backtest
from backtest.prices import adjusted_panels
from core.bootstrap import init
from core.calendar import TradingCalendar
from core.config import load_config
from core.outputs import report_dir
from data import store
from instruments.universe import IndexUniverse
from strategies.toy_lowvol import low_vol_weights


def _stats(nav, periods_per_year=252):
    ret = nav.pct_change().dropna()
    total = nav.iloc[-1] / nav.iloc[0] - 1
    years = len(nav) / periods_per_year
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan
    dd = (nav / nav.cummax() - 1).min()
    sharpe = (ret.mean() / ret.std() * np.sqrt(periods_per_year)) if ret.std() > 0 else np.nan
    return {"total_return": total, "cagr": cagr, "max_drawdown": dd, "sharpe": sharpe}


def run(start, end, index="000300.SH", n_select=20, lookback=20, init_cash=1_000_000.0,
        commission=0.0002, slippage=0.0005, cfg=None, root=None):
    cfg = cfg or load_config()
    log = init("toy_backtest")
    cal = TradingCalendar.load(cfg, root=root)
    if cal.source != "file":
        log.warning("交易日历为周内近似(非file),调仓日可能含节假日;建议先补 trade_cal")

    uni = IndexUniverse(index, root=root, cfg=cfg)
    symbols = uni.all_symbols()
    log.info("universe=%s 历史成分全集 %d 只", index, len(symbols))

    # 价格面板:留 lookback 缓冲以便首个调仓日有足够历史算波动率
    buffer_start = (pd.Timestamp(start) - pd.Timedelta(days=lookback * 3 + 30)).strftime("%Y-%m-%d")
    log.info("加载后复权价格面板 %s → %s ...", buffer_start, end)
    opens, closes = adjusted_panels(symbols, buffer_start, end, root=root, cfg=cfg, method="hfq")
    log.info("面板 shape: opens=%s closes=%s", opens.shape, closes.shape)

    reb_dates = [d.strftime("%Y-%m-%d") for d in cal.rebalance_dates(start, end, "monthly_first")]
    log.info("月频调仓日 %d 个(%s → %s)", len(reb_dates), reb_dates[0], reb_dates[-1])

    weights = low_vol_weights(reb_dates, uni, closes, n_select=n_select, lookback=lookback)
    nonempty = sum(1 for w in weights.values() if w)
    log.info("有效调仓日 %d/%d(每期选 %d 只)", nonempty, len(reb_dates), n_select)

    cost = CostModel(commission_rate=commission, slippage_rate=slippage, min_commission=0.0)
    win_closes = closes.loc[closes.index >= pd.Timestamp(start)]
    win_opens = opens.loc[opens.index >= pd.Timestamp(start)]
    res = run_backtest(reb_dates, weights, win_opens, win_closes, init_cash=init_cash, cost=cost)
    nav = res["nav"]

    # 基准:指数收盘归一
    bench = store.read_table("index_daily", start=start, end=end, symbols=[index], root=root, cfg=cfg)
    bench = bench.set_index("date")["close"].sort_index()
    bench = bench.reindex(nav.index).ffill()
    bench_nav = bench / bench.iloc[0] * init_cash

    strat_stats, bench_stats = _stats(nav), _stats(bench_nav)
    excess = strat_stats["cagr"] - bench_stats["cagr"]

    out_dir = report_dir("引擎调研", cfg=cfg, root=root)
    nav_df = pd.DataFrame({"date": nav.index, "strategy_nav": nav.values, "benchmark_nav": bench_nav.values})
    nav_df.to_csv(os.path.join(out_dir, "self_built_nav.csv"), index=False, encoding="utf-8-sig")
    res["trades"].to_csv(os.path.join(out_dir, "self_built_trades.csv"), index=False, encoding="utf-8-sig")

    log.info("=== 自研引擎玩具策略结果(%s → %s) ===", start, end)
    log.info("策略: 总收益 %.1f%% | 年化 %.2f%% | 最大回撤 %.1f%% | 夏普 %.2f",
             strat_stats["total_return"] * 100, strat_stats["cagr"] * 100,
             strat_stats["max_drawdown"] * 100, strat_stats["sharpe"])
    log.info("基准(%s): 年化 %.2f%% | 最大回撤 %.1f%% | 夏普 %.2f", index,
             bench_stats["cagr"] * 100, bench_stats["max_drawdown"] * 100, bench_stats["sharpe"])
    log.info("年化超额 %.2f%% | 成交笔数 %d | 产出 %s", excess * 100, len(res["trades"]), out_dir)
    return {"strategy": strat_stats, "benchmark": bench_stats, "excess_cagr": excess,
            "trades": len(res["trades"]), "out_dir": out_dir, "nav": nav}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2011-06-01")
    ap.add_argument("--end", default="2022-06-30")
    ap.add_argument("--index", default="000300.SH")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--lookback", type=int, default=20)
    args = ap.parse_args(argv)
    run(args.start, args.end, index=args.index, n_select=args.n, lookback=args.lookback)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
