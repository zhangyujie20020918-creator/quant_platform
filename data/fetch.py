# coding: utf-8
"""数据拉取编排(任务卡_卡1 第一节第4条)。

对每张表:按来源优先级挑第一个 supports 的来源 → plan 出分片 → 逐片拉取
(已存在且封口的分片跳过=断点续传;未封口分片重拉)→ 单片失败重试后记 fetch_failures.csv
→ 来源整体不可用(鉴权/连接判为熔断)则切下一来源重新规划 → 合并。

CLI:
    python -m data.fetch --tables trade_cal,stock_basic --start 2010-01-01 --end 2026-08-26
    python -m data.fetch --status
"""
import csv
import datetime as _dt
import logging
import os

import pandas as pd

from core.config import ROOT, get, load_config
from data import store
from data.fetchers.base import SourceUnavailable
from data.schema import FIRST_BATCH, get_spec

log = logging.getLogger(__name__)


def _failures_path(root):
    return os.path.join(store.cache_root(root=root), "fetch_failures.csv")


def _record_failure(root, table, source, chunk, error):
    path = _failures_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "table", "source", "chunk", "error"])
        w.writerow([_dt.datetime.now().isoformat(timespec="seconds"), table, source, chunk, str(error)[:300]])


def _default_sources(cfg, root):
    """按 config data.source_priority 构造来源实例(延迟 import,便于测试注入 sources 绕过)。"""
    from data.fetchers.akshare import AksharesSource
    from data.fetchers.tushare import TushareSource
    registry = {"tushare": TushareSource, "akshare": AksharesSource}
    out = []
    for name in get(cfg, "data.source_priority", ["tushare"]):
        if name in registry:
            out.append(registry[name](cfg, root=root))
    return out


def fetch_table(table, start, end, sources=None, cfg=None, root=None, force=False):
    """拉一张表。返回 {source_used, fetched, skipped, failed}。"""
    cfg = cfg if cfg is not None else load_config()
    root = root or ROOT
    get_spec(table)   # 未注册表直接报错
    sources = sources if sources is not None else _default_sources(cfg, root)
    threshold = get(cfg, "data.fetch.source_fail_threshold", 5)

    candidates = [s for s in sources if s.supports(table)]
    if not candidates:
        raise LookupError("没有来源支持表 %r(已配置来源: %s)" % (table, [s.name for s in sources]))

    last_error = None
    for src in candidates:
        fetched = skipped = failed = consecutive = 0
        unavailable = False
        for chunk in src.plan(table, start, end):
            closed = not src.is_open_chunk(table, chunk)
            if closed and not force and store.has_part(table, src.name, chunk, root=root):
                skipped += 1
                continue
            try:
                df = src.fetch(table, chunk)
                store.write_part(table, src.name, chunk, df, root=root)
                fetched += 1
                consecutive = 0
            except SourceUnavailable as e:
                log.warning("来源 %s 不可用(%s),切换下一来源", src.name, e)
                last_error = e
                unavailable = True
                break
            except Exception as e:
                failed += 1
                consecutive += 1
                last_error = e
                _record_failure(root, table, src.name, chunk, e)
                log.warning("拉取 %s[%s] 分片 %s 失败: %s", table, src.name, chunk, e)
                if consecutive >= threshold:
                    log.warning("来源 %s 连续 %d 次失败,熔断切换", src.name, consecutive)
                    unavailable = True
                    break
        if unavailable:
            continue
        store.consolidate(table, cfg=cfg, root=root)
        return {"source_used": src.name, "fetched": fetched, "skipped": skipped, "failed": failed}

    raise RuntimeError("表 %s 所有来源均不可用,最后错误: %s" % (table, last_error))


def fetch_tables(tables, start=None, end=None, cfg=None, root=None, force=False):
    cfg = cfg if cfg is not None else load_config()
    root = root or ROOT
    start = start or get(cfg, "data.backfill_start", "2010-01-01")
    end = end or _dt.date.today().isoformat()
    results = {}
    for table in tables:
        log.info("=== 拉取 %s (%s → %s) ===", table, start, end)
        results[table] = fetch_table(table, start, end, cfg=cfg, root=root, force=force)
        log.info("%s 完成: %s", table, results[table])
    return results


def export_calendar(cfg=None, root=None):
    """从 trade_cal 表导出 core.calendar 用的 trading_days.csv(仅开市日)。"""
    cfg = cfg if cfg is not None else load_config()
    root = root or ROOT
    df = store.read_table("trade_cal", root=root)
    if df.empty:
        log.warning("trade_cal 表为空,跳过日历导出")
        return None
    exch = get(cfg, "calendar.exchange", "SSE")
    days = df[(df["exchange"] == exch) & (df["is_open"] == 1)]["date"].sort_values()
    rel = get(cfg, "calendar.file", "cache/calendar/trading_days.csv")
    out = rel if os.path.isabs(rel) else os.path.join(root, rel)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pd.DataFrame({"date": days.dt.strftime("%Y-%m-%d")}).to_csv(out, index=False)
    log.info("交易日历已导出 %s(%d 个开市日)", out, len(days))
    return out


def print_status(tables=None, root=None):
    from core.bootstrap import init
    init("data.fetch")
    for table in tables or FIRST_BATCH:
        st = store.table_status(table, root=root)
        rng = "%s→%s" % (st["date_min"], st["date_max"]) if st["date_min"] else "(静态)"
        print("%-14s rows=%-9d parts=%-5d %s  sources=%s"
              % (table, st["rows"], st["parts"], rng, st["sources"] or "-"))


def main(argv=None):
    import argparse
    from core.bootstrap import init
    init("data.fetch")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", default=None, help="逗号分隔;缺省=首批全部")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--status", action="store_true", help="只打印各表状态,不拉取")
    ap.add_argument("--export-calendar", action="store_true", help="拉取后从 trade_cal 导出交易日历文件")
    args = ap.parse_args(argv)

    tables = args.tables.split(",") if args.tables else list(FIRST_BATCH)
    if args.status:
        print_status(tables)
        return 0
    fetch_tables(tables, args.start, args.end, force=args.force)
    if args.export_calendar or "trade_cal" in tables:
        export_calendar()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
