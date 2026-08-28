# coding: utf-8
"""S1 数据体检四项(任务卡_卡1 第一节第5条 / SOP S1)。

四项:①退市样本在否(防幸存者偏差)②PIT 时点正确性 ③脏值扫描 ④逐日覆盖曲线。
阈值全部来自 config.quality(批前声明)。产出 reports/{日期}_数据体检/quality_report.md + csv。
CLI:python -m data.quality
"""
import datetime as _dt
import logging
import os

import pandas as pd

from core.config import get, load_config
from core.outputs import report_dir
from data import store

log = logging.getLogger(__name__)


# ---------- ① 退市样本 ----------

def check_delisting(cfg, root=None):
    min_count = get(cfg, "quality.min_delisted_count", 100)
    basic = store.read_table("stock_basic", root=root)
    delisted = basic[basic["list_status"] == "D"] if len(basic) else basic
    count = int(len(delisted))
    with_history = 0
    if count:
        daily_syms = set(store.read_table("stock_daily", columns=["symbol"], root=root)["symbol"].unique())
        with_history = int(delisted["symbol"].isin(daily_syms).sum())
    return {"check": "delisting", "passed": count >= min_count, "delisted_count": count,
            "delisted_with_history": with_history, "threshold": min_count}


# ---------- ② PIT 时点正确性 ----------

def check_pit(cfg, root=None):
    max_gap = get(cfg, "quality.max_snapshot_gap_days", 45)
    cal = store.read_table("trade_cal", root=root)
    exch = get(cfg, "calendar.exchange", "SSE")
    open_days = cal[(cal["exchange"] == exch) & (cal["is_open"] == 1)]["date"] if len(cal) else pd.Series([], dtype="datetime64[ns]")
    latest_open = open_days.max() if len(open_days) else None

    daily = store.read_table("stock_daily", columns=["date"], root=root)
    after = int((daily["date"] > latest_open).sum()) if (latest_open is not None and len(daily)) else 0

    weights = store.read_table("index_weight", root=root)
    max_snapshot_gap = 0
    if len(weights):
        for _, grp in weights.groupby("index_symbol"):
            snaps = grp["date"].drop_duplicates().sort_values()
            if len(snaps) > 1:
                gap = snaps.diff().dropna().dt.days.max()
                max_snapshot_gap = max(max_snapshot_gap, int(gap))

    passed = after == 0 and (max_snapshot_gap <= max_gap)
    return {"check": "pit", "passed": passed, "daily_after_calendar": after,
            "latest_open_day": None if latest_open is None else latest_open.date().isoformat(),
            "max_snapshot_gap": max_snapshot_gap, "gap_threshold": max_gap}


# ---------- ③ 脏值扫描 ----------

def check_dirty(cfg, root=None):
    max_ratio = get(cfg, "quality.max_dirty_ratio", 0.001)
    daily = store.read_table("stock_daily", root=root)
    n = len(daily)
    reasons = {}
    mask = pd.Series(False, index=daily.index)
    if n:
        price_bad = (daily[["open", "high", "low", "close"]] <= 0).any(axis=1)
        hl_bad = daily["high"] < daily["low"]
        vol_bad = daily["volume"] < 0
        gap_bad = daily["close"].isna() & (daily["volume"] > 0)
        for name, m in [("price<=0", price_bad), ("high<low", hl_bad),
                        ("volume<0", vol_bad), ("close_na_with_volume", gap_bad)]:
            c = int(m.sum())
            if c:
                reasons[name] = c
            mask = mask | m
    dirty = int(mask.sum())
    ratio = (dirty / n) if n else 0.0
    return {"check": "dirty", "passed": ratio <= max_ratio, "rows": n, "dirty_rows": dirty,
            "dirty_ratio": ratio, "threshold": max_ratio, "reasons": reasons}


# ---------- ④ 逐日覆盖曲线 ----------

def check_coverage(cfg, root=None):
    min_cov = get(cfg, "quality.min_daily_coverage", 0.95)
    daily = store.read_table("stock_daily", columns=["date", "symbol"], root=root)
    basic = store.read_table("stock_basic", root=root)
    if not len(daily) or not len(basic):
        return {"check": "coverage", "passed": not len(daily), "low_coverage_days": 0,
                "min_coverage": None, "threshold": min_cov, "curve": []}
    # 每交易日应在册数:上市≤当日 且 (未退市 或 退市日≥当日)
    per_day = daily.groupby("date")["symbol"].nunique()
    list_date = pd.to_datetime(basic["list_date"], errors="coerce")
    delist_date = pd.to_datetime(basic["delist_date"], errors="coerce")
    covs = []
    for d, have in per_day.items():
        listed = (list_date <= d) | list_date.isna()
        alive = delist_date.isna() | (delist_date >= d)
        eligible = int((listed & alive).sum())
        cov = have / eligible if eligible else 1.0
        covs.append({"date": d.date().isoformat(), "have": int(have), "eligible": eligible, "coverage": cov})
    curve = pd.DataFrame(covs)
    low = curve[curve["coverage"] < min_cov]
    return {"check": "coverage", "passed": low.empty, "low_coverage_days": int(len(low)),
            "min_coverage": float(curve["coverage"].min()), "threshold": min_cov,
            "curve": curve.to_dict("records")}


# ---------- 汇总与报告 ----------

_CHECKS = [("delisting", check_delisting, "① 退市样本在否(防幸存者偏差)"),
           ("pit", check_pit, "② PIT 时点正确性"),
           ("dirty", check_dirty, "③ 脏值扫描"),
           ("coverage", check_coverage, "④ 逐日覆盖曲线")]


def run_all(cfg=None, root=None, date=None):
    cfg = cfg if cfg is not None else load_config()
    results = {}
    for key, fn, _ in _CHECKS:
        results[key] = fn(cfg, root=root)
        log.info("%s: %s", key, "通过" if results[key]["passed"] else "未通过")
    out_dir = report_dir("数据体检", date=date, cfg=cfg, root=root)
    _write_report(out_dir, results, cfg)
    return {"checks": results, "all_passed": all(r["passed"] for r in results.values()), "report_dir": out_dir}


def _write_report(out_dir, results, cfg):
    lines = ["# 数据体检报告", "",
             "生成时间:%s" % _dt.datetime.now().isoformat(timespec="seconds"),
             "阈值口径(config.quality,批前声明):%s" % (get(cfg, "quality", {})), ""]
    for key, _, title in _CHECKS:
        r = results[key]
        lines.append("## %s — %s" % (title, "通过 ✅" if r["passed"] else "未通过 ❌"))
        for k, v in r.items():
            if k in ("check", "passed", "curve"):
                continue
            lines.append("- %s: %s" % (k, v))
        lines.append("")
    # 覆盖曲线单独落 csv
    cov = results["coverage"].get("curve")
    if cov:
        pd.DataFrame(cov).to_csv(os.path.join(out_dir, "coverage_curve.csv"), index=False, encoding="utf-8-sig")
        lines.append("覆盖曲线明细:coverage_curve.csv")
    with open(os.path.join(out_dir, "quality_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    import argparse
    from core.bootstrap import init
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="报告归档日期(默认今天)")
    args = ap.parse_args(argv)
    init("data.quality")
    summary = run_all(date=args.date)
    print("体检完成:%s;报告 %s" % ("全部通过" if summary["all_passed"] else "存在未通过项", summary["report_dir"]))
    return 0 if summary["all_passed"] else 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
