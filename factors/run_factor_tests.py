# coding: utf-8
"""因子检验入口(卡4 里程碑):注册表 → universe(PIT)→ 面板 → 前瞻收益(T+1 锁死)→ 管线 → 报告 + tear sheet。

判据先于数据:报告文件先写"批前声明"一节(阈值/切分/候选数,全部来自 config.protocol),再算任何数字。
用法:python -m factors.run_factor_tests [--date 2026-08-28] [--factors vol_20,rev_20] [--universe 000300.SH]
"""
from core.bootstrap import init  # noqa: F401  必须第一行

import argparse
import datetime as dt
import os
import time
import warnings

import numpy as np
import pandas as pd

from backtest.prices import adjusted_panels
from core.calendar import TradingCalendar
from core.config import ROOT, get, load_config
from core.outputs import report_dir, run_dir
from data import store
from factors.alphalens_wrapper import tear_sheet
from factors.forward_returns import forward_returns
from factors.lib import load_factor
from factors.pipeline import declaration, run_batch
from factors.registry import DEFAULT_PATH, load_registry
from instruments.universe import IndexUniverse

warnings.filterwarnings("ignore", category=FutureWarning)
TOPIC = "卡4因子检验"
PANEL_BUFFER_DAYS = 400      # 面板起点提前的自然日数(覆盖最长 lookback 120 交易日 + 余量)


def _fmt(v, nd=4):
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else ("%.*f" % (nd, v) if isinstance(v, float) else str(v))


def write_declaration(path, decl, ids, universe):
    lines = [
        "# 卡4 因子检验报告(%s)" % decl["declared_at"], "",
        "## 一、批前声明(判据先于数据;写于任何统计计算之前)", "",
        "- universe:%s 历史成分(PIT,按信号日取最近一次快照)" % universe,
        "- 信号日频率 %s;前瞻收益 = open[T+1+%d] / open[T+1] − 1(T+1 口径锁死);分组数 %d"
        % (decl["signal_freq"], decl["holding_days"], decl["n_quantiles"]),
        "- 样本内 %s ~ %s;样本外 %s ~ %s(**每因子只评估一次,结果即终审**)"
        % (decl["in_sample"][0], decl["in_sample"][1], decl["out_of_sample"][0], decl["out_of_sample"][1]),
        "- 阈值(config.protocol):" + ",".join("%s=%s" % (k, v) for k, v in decl["thresholds"].items()),
        "- 本批因子 %d 个(%s),其中候选 %d 个(其余为对照组:阳性 rev_20 / 阴性 random_control)" % (len(ids), ", ".join(ids), decl["n_candidates"]),
        "- active ⇔ 样本内 |IC|≥ic_min ∧ |ICIR|≥icir_min ∧ |单调性|≥monotonicity_min ∧ 样本外同号且保留≥oos_retention_min ∧ BH 显著;"
        "有信号但不满足 → tested_weak;无信号 → rejected", "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def append_results(path, result, reg, tear_dirs, elapsed):
    rows = result["rows"]
    lines = ["## 二、裁决总表", "",
             "| 因子 | 角色 | IC_is | ICIR_is | n_is | t | p(BH校正) | 单调性 | top组换手 | IC_oos | ICIR_oos | n_oos | 裁决 | 方向 | 冗余 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for fid, r in rows.items():
        lines.append("| %s | %s | %s | %s | %d | %s | %s | %s | %s | %s | %s | %d | **%s**%s | %s | %s |" % (
            fid, r["role"], _fmt(r["ic_is"]), _fmt(r["icir_is"], 3), r["n_is"], _fmt(r["t_is"], 2),
            _fmt(r["p_adj"], 4), _fmt(r["monotonicity"], 2), _fmt(r["turnover"], 2), _fmt(r["ic_oos"]),
            _fmt(r["icir_oos"], 3), r["n_oos"], r["verdict"], "(沿用终审)" if r["oos_skipped"] else "",
            reg[fid]["direction"], ", ".join(r["redundant_with"]) or "—"))
    lines += ["", "## 三、对照组", ""] + ["- %s:%s" % (k, v) for k, v in result["controls"].items()]
    lines += ["", "## 四、分组平均前瞻收益(样本内,组1=因子最低)", ""]
    for fid, r in rows.items():
        qr = r["quantile_returns_is"]
        lines.append("- %s:%s" % (fid, " | ".join("Q%d %.4f" % (k, v) for k, v in sorted(qr.items()))))
    lines += ["", "## 五、tear sheet(alphalens,T+1 开盘口径)", ""]
    for fid, d in tear_dirs.items():
        lines.append("- %s:`%s`" % (fid, os.path.relpath(d, ROOT).replace(os.sep, "/") if os.path.isdir(str(d)) else d))
    lines += ["", "## 六、局限声明", "",
              "- 月频信号 × 20 日持有,样本内约 %d 个截面,t 检验功效有限;结论只对该 universe(大盘股)有效。" % max(r["n_is"] for r in rows.values()),
              "- 阳性对照首批只能建立基线,不能证明管线正确;第二批起才构成真正的阳性检验。",
              "- 因子面板只用价格(后复权),未做行业/市值中性化;IC 为 Spearman 秩相关。",
              "- 耗时 %.0f 秒。" % elapsed, ""]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--factors", default=None, help="逗号分隔;默认注册表内全部非 rejected 因子 + 对照组")
    ap.add_argument("--universe", default="000300.SH")
    args = ap.parse_args()
    log = init("factor_tests")
    t0 = time.time()
    cfg = load_config()
    p = get(cfg, "protocol")
    reg = load_registry(DEFAULT_PATH)
    if args.factors:
        ids = [x.strip() for x in args.factors.split(",") if x.strip()]
    else:
        ids = [fid for fid, e in reg.items() if e["role"] != "candidate" or e["status"] != "rejected"]
    today = dt.date.fromisoformat(args.date)

    out_dir = report_dir(TOPIC, date=args.date)
    report = os.path.join(out_dir, "factor_verdict.md")
    decl = declaration(cfg, n_candidates=sum(1 for f in ids if reg[f]["role"] == "candidate"), today=today)
    write_declaration(report, decl, ids, args.universe)          # ← 先写声明
    log.info("批前声明已写入 %s", report)

    uni = IndexUniverse(args.universe)
    symbols = uni.all_symbols()
    cal = TradingCalendar.load(cfg)
    if cal.source != "file":
        raise RuntimeError("交易日历非文件模式,拒绝检验")
    is_start, oos_end = pd.Timestamp(p["in_sample"][0]), pd.Timestamp(p["out_of_sample"][1])
    panel_start = (is_start - pd.Timedelta(days=PANEL_BUFFER_DAYS)).strftime("%Y-%m-%d")
    log.info("加载 %d 只后复权面板 %s → %s ...", len(symbols), panel_start, oos_end.date())
    opens, closes = adjusted_panels(symbols, panel_start, oos_end, method="hfq", fields=("open", "close"))
    signal_days = cal.rebalance_dates(is_start, oos_end, p["signal_freq"])
    signal_days = signal_days[signal_days.isin(closes.index)]
    fwd = forward_returns(opens, int(p["holding_days"])).reindex(signal_days)
    log.info("信号日 %d 个;前瞻收益面板 %s", len(signal_days), fwd.shape)

    # PIT 成分掩码:信号日 d 只保留当日成分
    mask = pd.DataFrame(False, index=signal_days, columns=closes.columns)
    for d in signal_days:
        cons = [s for s in uni.constituents(d) if s in mask.columns]
        mask.loc[d, cons] = True
    ctx = {"close": closes, "open": opens, "cfg": cfg}
    panels = {}
    for fid in ids:
        f = load_factor(fid).compute(ctx).reindex(index=signal_days, columns=closes.columns)
        panels[fid] = f.where(mask)
        log.info("因子 %s 面板就绪,有效值 %d", fid, int(panels[fid].notna().sum().sum()))

    data_version = store.date_range("stock_daily")[1].date().isoformat()
    result = run_batch(panels, fwd, DEFAULT_PATH, cfg, report=os.path.relpath(report, ROOT).replace(os.sep, "/"),
                       data_version=data_version, today=today)
    for fid, r in result["rows"].items():
        log.info("%-15s IC_is=%s ICIR=%s mono=%s IC_oos=%s → %s", fid, _fmt(r["ic_is"]), _fmt(r["icir_is"], 3),
                 _fmt(r["monotonicity"], 2), _fmt(r["ic_oos"]), r["verdict"])

    # tear sheet:alphalens 要求因子日期与交易日历同频,故喂全日频面板(信号日子集不满足其校验);
    # 正式裁决仍以上面月频非重叠统计为准,tear sheet 是日频重叠口径的可视化
    daily_days = closes.index[(closes.index >= is_start) & (closes.index <= oos_end)]
    daily_mask = pd.DataFrame(False, index=daily_days, columns=closes.columns)
    for d in daily_days:
        cons = [s for s in uni.constituents(d) if s in daily_mask.columns]
        daily_mask.loc[d, cons] = True
    tear_dirs = {}
    for fid in ids:
        if reg[fid]["role"] == "negative_control":
            continue
        d = run_dir(TOPIC, "tear_" + fid, date=args.date)
        try:
            daily_panel = load_factor(fid).compute(ctx).reindex(index=daily_days, columns=closes.columns).where(daily_mask)
            tear_sheet(daily_panel, opens, d, periods=p["alphalens_periods"], quantiles=int(p["n_quantiles"]), name=fid)
            tear_dirs[fid] = d
            log.info("tear sheet %s → %s", fid, d)
        except Exception as e:      # tear sheet 失败不应拖垮裁决;如实记录
            log.error("tear sheet %s 失败: %s", fid, e)
            tear_dirs[fid] = "失败: %s" % e
    reg_after = load_registry(DEFAULT_PATH)
    append_results(report, result, reg_after, tear_dirs, time.time() - t0)
    print("报告:", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
