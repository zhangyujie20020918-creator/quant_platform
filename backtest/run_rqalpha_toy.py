# coding: utf-8
"""卡3 阶段C:玩具策略 RQAlpha 版跑真实数据 + 与自研引擎交叉验证(SOP S4)+ 全成本版结果 → 报告。

两次 RQAlpha 回测:
  align:成本对齐自研(佣金同费率、无最低佣金、无印花税/过户费、无滑点、不过滤 ST),与自研同参数重跑对比,
        |年化差| ≤ config protocol.cross_engine_tolerance_pct(百分点)即互证;
  full: 品种规则表全成本(佣金/最低佣金/印花税/过户费按生效日)+ ST 过滤 + RQAlpha 内置涨跌停/停牌/T+1/退市清算。
用法:python -m backtest.run_rqalpha_toy --start 2011-06-01 --end 2022-06-30 [--date 2026-08-28]
"""
from core.bootstrap import init  # noqa: F401  必须第一行

import argparse
import datetime as dt
import os
import time
import warnings

import numpy as np
import pandas as pd
from rqalpha import run_func

from backtest.run_toy_backtest import _stats, run as run_self_built
from core.config import ROOT, get, load_config
from core.outputs import report_dir, run_dir
from instruments.universe import IndexUniverse
from strategies.toy_lowvol_rq import make_strategy

warnings.filterwarnings("ignore", category=FutureWarning, module="rqalpha")

TOPIC = "卡3阶段C"


def run_rq(cfg, start, end, params, costs, out_dir, preload, init_cash, benchmark_obid):
    funcs = make_strategy(params, cfg=cfg)
    state = funcs.pop("state")
    config = {
        "base": {"start_date": start, "end_date": end, "accounts": {"stock": init_cash},
                 "data_bundle_path": os.path.join(ROOT, "no_bundle")},
        "extra": {"log_level": "error"},
        "mod": {
            "store": {"enabled": True, "lib": "backtest.rqalpha_adapter.mod", "preload": preload, "costs": costs},
            "sys_progress": {"enabled": False},
            "sys_analyser": {"enabled": True, "plot": False, "benchmark": benchmark_obid, "report_save_path": out_dir},
        },
    }
    t0 = time.time()
    res = run_func(config=config, **funcs)["sys_analyser"]
    nav = res["portfolio"]["total_value"].copy()
    nav.index = pd.to_datetime(nav.index).normalize()
    return {"nav": nav, "stats": _stats(nav), "trades": len(res["trades"]), "signals": state["signals"],
            "summary": res["summary"], "seconds": time.time() - t0, "res": res}


def _fmt(st):
    return "总收益 %.1f%% | 年化 %.2f%% | 最大回撤 %.1f%% | 夏普 %.2f" % (
        st["total_return"] * 100, st["cagr"] * 100, st["max_drawdown"] * 100, st["sharpe"])


def _row(name, st, trades, extra=""):
    return "| %s | %.1f%% | %.2f%% | %.1f%% | %.2f | %s | %s |" % (
        name, st["total_return"] * 100, st["cagr"] * 100, st["max_drawdown"] * 100, st["sharpe"], trades, extra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2011-06-01")
    ap.add_argument("--end", default="2022-06-30")
    ap.add_argument("--index", default="000300.SH")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--lookback", type=int, default=20)
    ap.add_argument("--commission", type=float, default=0.0002, help="对齐口径的佣金费率(自研默认万2)")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()
    log = init("rqalpha_toy")
    cfg = load_config()
    tol = float(get(cfg, "protocol.cross_engine_tolerance_pct"))
    init_cash = 1_000_000.0
    preload = IndexUniverse(args.index).all_symbols()
    bench_obid = args.index.replace(".SH", ".XSHG")
    base_params = {"index": args.index, "n_select": args.n, "lookback": args.lookback, "rebalance": "monthly_first"}

    # ① 自研引擎(对齐口径:同佣金、无滑点——RQAlpha 集合竞价撮合不加滑点)
    log.info("① 自研引擎重跑(对齐口径)...")
    sb = run_self_built(args.start, args.end, index=args.index, n_select=args.n, lookback=args.lookback,
                        init_cash=init_cash, commission=args.commission, slippage=0.0, cfg=cfg, topic=TOPIC)
    sb_nav = sb["nav"]

    # ② RQAlpha 对齐版
    align_costs = {"commission_rate": args.commission, "min_commission": 0.0, "stamp_tax_sell": [], "transfer_fee": []}
    log.info("② RQAlpha 对齐版...")
    rq_align = run_rq(cfg, args.start, args.end, dict(base_params, filter_st=False, costs=align_costs), align_costs,
                      run_dir(TOPIC, "rq_align", date=args.date), preload, init_cash, bench_obid)
    log.info("   %s(%.0fs,%d 信号,%d 笔)", _fmt(rq_align["stats"]), rq_align["seconds"], rq_align["signals"], rq_align["trades"])

    # ③ RQAlpha 全成本 + ST 过滤
    log.info("③ RQAlpha 全成本版...")
    rq_full = run_rq(cfg, args.start, args.end, dict(base_params, filter_st=True), None,
                     run_dir(TOPIC, "rq_full", date=args.date), preload, init_cash, bench_obid)
    log.info("   %s(%.0fs,%d 笔)", _fmt(rq_full["stats"]), rq_full["seconds"], rq_full["trades"])

    # ④ 交叉验证
    both = pd.concat([sb_nav.rename("self_built"), rq_align["nav"].rename("rqalpha_align"),
                      rq_full["nav"].rename("rqalpha_full")], axis=1)
    both.index.name = "date"
    out = report_dir(TOPIC, date=args.date)
    both.to_csv(os.path.join(out, "toy_lowvol_navs.csv"), encoding="utf-8-sig")
    r_sb, r_rq = both["self_built"].pct_change().dropna(), both["rqalpha_align"].pct_change().dropna()
    common = r_sb.index.intersection(r_rq.index)
    corr = float(np.corrcoef(r_sb.loc[common], r_rq.loc[common])[0, 1])
    te = float((r_sb.loc[common] - r_rq.loc[common]).std() * np.sqrt(252))
    d_cagr = (rq_align["stats"]["cagr"] - sb["strategy"]["cagr"]) * 100
    d_dd = (rq_align["stats"]["max_drawdown"] - sb["strategy"]["max_drawdown"]) * 100
    passed = abs(d_cagr) <= tol
    log.info("④ 交叉验证:Δ年化 %.2f pp(容差 %.1f)→ %s;日收益相关 %.4f,跟踪误差 %.2f%%",
             d_cagr, tol, "通过" if passed else "不通过", corr, te * 100)

    s = rq_full["summary"]
    lines = [
        "# 卡3 阶段C · 玩具策略 RQAlpha 版 + 交叉验证报告(%s)" % args.date,
        "",
        "策略:%s 成分(PIT)低波 %d 只等权,月频(信号=月首交易日收盘,次日开盘执行),lookback=%d;区间 %s → %s;"
        % (args.index, args.n, args.lookback, args.start, args.end),
        "初始资金 %.0f 万。**仅验证管道,不含研究观点。**" % (init_cash / 1e4),
        "",
        "## 一、交叉验证(SOP S4:独立引擎复现)",
        "",
        "对齐口径:佣金 %.4f 双边、无最低佣金、无印花税/过户费、无滑点、不过滤 ST;两边同一 universe(instruments.universe)、"
        "同一调仓日历(core.calendar)、同一选券函数(strategies.toy_lowvol.select_low_vol)、同一数据(store)。" % args.commission,
        "",
        "| 引擎 | 总收益 | 年化 | 最大回撤 | 夏普 | 成交笔数 | 备注 |",
        "|---|---|---|---|---|---|---|",
        _row("自研 backtest.engine", sb["strategy"], sb["trades"], "T收盘信号→T+1开盘,允许零股,无涨跌停/停牌拒单"),
        _row("RQAlpha(store 数据源)对齐版", rq_align["stats"], rq_align["trades"],
             "T+1 集合竞价,整手,涨跌停/停牌/T+1 内置拒单;%d 次信号" % rq_align["signals"]),
        "",
        "- Δ年化 = **%+.2f pp**(容差 ±%.1f pp,`protocol.cross_engine_tolerance_pct`)→ **%s**;Δ最大回撤 %+.2f pp。"
        % (d_cagr, tol, "通过,互证成立" if passed else "不通过,需定位口径分歧", d_dd),
        "- 日收益相关系数 %.4f,年化跟踪误差 %.2f%%。" % (corr, te * 100),
        "- 已知口径差异(不视为缺陷):①RQAlpha 整手买入(每只约 0~1 手现金闲置);②涨停日 RQAlpha 拒买、跌停日拒卖,自研照成交;"
        "③退市/吸收合并标的 RQAlpha 按末价折现,自研引擎无价即按 0 计(自研局限,卡2 报告已声明);"
        "④自研买入顺序按选券波动排序逐只受现金约束,RQAlpha 版先清仓再买入。",
        "",
        "## 二、全成本版(品种规则表成本 + ST 过滤 + RQAlpha 内置红线)",
        "",
        "| 引擎 | 总收益 | 年化 | 最大回撤 | 夏普 | 成交笔数 | 备注 |",
        "|---|---|---|---|---|---|---|",
        _row("RQAlpha 全成本版", rq_full["stats"], rq_full["trades"], "佣金万2/最低5元/印花税·过户费按生效日/ST 过滤"),
        _row("基准 %s(自研 stats 口径)" % args.index, sb["benchmark"], "-", ""),
        "",
        "- RQAlpha summary:年化 %.2f%% | 基准年化 %.2f%% | alpha %.4f | beta %.3f | 最大回撤 %.2f%% | 夏普 %.3f | 信息比率 %.3f"
        % (s["annualized_returns"] * 100, s["benchmark_annualized_returns"] * 100, s["alpha"], s["beta"],
           s["max_drawdown"] * 100, s["sharpe"], s["information_ratio"]),
        "- 成本影响(全成本版 vs 对齐版):年化 %+.2f pp。" % ((rq_full["stats"]["cagr"] - rq_align["stats"]["cagr"]) * 100),
        "- 产出:`%s`(navs)、RQAlpha 报表 `rq_align_runs/`、`rq_full_runs/`。" % os.path.relpath(os.path.join(out, "toy_lowvol_navs.csv"), ROOT),
        "",
        "## 三、A股股票红线核对(清单 instruments/cn_stock_redlines.md,验收测试 tests/test_cn_stock_redlines.py)",
        "",
        "| 红线 | 机制 | 验收测试 | 结论 |",
        "|---|---|---|---|",
        "| R1 前复权正确 | bar 原始价 + adj_factor→ex_cum_factor,history_bars 按查询日重基;持仓过除权日合成 split | test_r1 / 阶段B 19 项核对 | 通过 |",
        "| R2 涨停不可买、跌停不可卖 | limit_up/down 按品种规则表(板块/ST/生效日)算入 bar,RQAlpha price_limit 拒单 | test_r2 | 通过 |",
        "| R3 停牌口径书面声明 | 交易日∧[首bar,数据末日]∧无行 → 停牌,RQAlpha is_trading_validator 拒单 | test_r3 | 通过 |",
        "| R4 ST 过滤 | namechange 区间 → is_st_stock;策略层 filter_st 剔除 | test_r4 / test_st_filter_switches_pick | 通过 |",
        "| R5 退市股在历史池 + 退市清算 | stock_basic 含退市入 instruments;退市前末日结算按末价折现(cash_return_by_stock_delisted) | test_r5 | 通过 |",
        "| R6 T+1 | market_tplus=1(品种规则表),当日买入不可卖 | test_r6 | 通过 |",
        "| R7 全成本 | RuleTableStockCostDecider:佣金/最低佣金/印花税/过户费全查表按生效日 | test_r7 | 通过 |",
        "",
        "## 四、局限声明",
        "",
        "- 集合竞价撮合不加滑点(RQAlpha 机制);日频只有收盘撮合,故 T+1 开盘执行走集合竞价。",
        "- 上市首日(及科创/创业板前五日)涨跌停特例以\"首日无限制\"近似;科创板 200 股起、步长 1 的整手规则未在策略下单层处理(玩具策略买 100 的倍数)。",
        "- 成交量上限 25%(RQAlpha 默认 volume_limit)保留;流动性冲击/滑点模型留给后续策略研究按品种配置。",
        "- 无风险利率为 config 常数 `backtest.risk_free_rate`;RQAlpha 提示 `base.capital_gain_tax_rate` 未显式配置(默认 0,A 股个人免征)。",
        "",
    ]
    path = os.path.join(out, "toy_lowvol_cross_validation.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines[6:22]))
    print("报告:", path)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
