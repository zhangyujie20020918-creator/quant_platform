# coding: utf-8
"""卡0 验收物:空管道冒烟——config加载 → example结构同步校验 → outputs落盘 → 日历可查。

可重复运行;任何一步失败即非零退出。产出一份 reports/{今天}_卡0奠基/smoke.md 作为记录。
用法:.venv/Scripts/python tools/smoke_pipeline.py
"""
import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.bootstrap import init          # noqa: E402  所有入口第一件事
from core.calendar import TradingCalendar  # noqa: E402
from core.config import check_example_sync, get, load_config  # noqa: E402
from core.outputs import report_dir, run_dir  # noqa: E402


def main():
    log = init("smoke")
    lines = []

    cfg = load_config()
    lines.append("config 加载 OK:protocol.ic_min=%s,data.backfill_start=%s"
                 % (get(cfg, "protocol.ic_min"), get(cfg, "data.backfill_start")))

    diffs = check_example_sync()
    if diffs:
        for d in diffs:
            log.error("config 与 example 结构不一致: %s", d)
        return 1
    lines.append("config.yaml 与 config.example.yaml 结构一致 OK")

    cal = TradingCalendar.load(cfg)
    today = _dt.date.today()
    nxt = cal.next_trading_day(today)
    rb = cal.rebalance_dates(today.replace(day=1), today.replace(month=12, day=31))
    lines.append("日历可查 OK:source=%s,今天是否交易日=%s,下一交易日=%s,今年剩余月度调仓日=%d个"
                 % (cal.source, cal.is_trading_day(today), nxt.date(), len(rb)))
    if cal.source != "file":
        lines.append("  (注意:当前为周内近似模式,不含节假日;卡1落盘真实日历后自动切换)")

    rd = report_dir("卡0奠基")
    rr = run_dir("卡0奠基", "smoke")
    lines.append("outputs 落盘 OK:%s / %s" % (os.path.relpath(rd, get(cfg, "meta.reports_dir", "reports")),
                                            os.path.basename(rr)))

    out = os.path.join(rd, "smoke.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("# 卡0 空管道冒烟记录\n\n运行时间:%s\n\n" % _dt.datetime.now().isoformat(timespec="seconds"))
        f.write("\n".join("- " + s for s in lines) + "\n")
    for s in lines:
        log.info(s)
    log.info("冒烟记录已写入 %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
