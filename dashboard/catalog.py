# coding: utf-8
"""reports/ 目录扫描(纯函数,只读;蓝图原则7:面板只读 reports 永不写)。

识别 `reports/{YYYY-MM-DD}_{topic}/` 下:RQAlpha 回测报表(`*_runs/` 含 portfolio.csv 等)、净值对比(`*_navs.csv`)、
因子批次(`factor_verdict.md` + `tear_<id>_runs/`)、信号(`{date}_信号_{strategy}/orders_*.csv` + signal_log.md)、
以及所有顶层 md 报告。最新日期在前。
"""
import os
import re
from dataclasses import dataclass, field

DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")
RQ_FILES = {"portfolio": "portfolio.csv", "trades": "trades.csv", "positions": "stock_positions.csv", "summary": "summary.xlsx"}
SIGNAL_PREFIX = "信号_"


@dataclass
class ReportDir:
    date: str
    topic: str
    path: str
    markdowns: list = field(default_factory=list)

    @property
    def label(self):
        return "%s %s" % (self.date, self.topic)


@dataclass
class BacktestRun:
    date: str
    topic: str
    name: str
    path: str
    files: dict

    @property
    def label(self):
        return "%s %s / %s" % (self.date, self.topic, self.name)


@dataclass
class NavFile:
    date: str
    topic: str
    path: str
    columns: list

    @property
    def label(self):
        return "%s %s / %s" % (self.date, self.topic, os.path.basename(self.path))


@dataclass
class FactorBatch:
    date: str
    topic: str
    path: str
    verdict_md: str
    tear_sheets: dict

    @property
    def label(self):
        return "%s %s" % (self.date, self.topic)


@dataclass
class SignalSet:
    date: str
    strategy: str
    path: str
    orders: list
    log: str

    @property
    def label(self):
        return "%s %s" % (self.date, self.strategy)


@dataclass
class Catalog:
    root: str
    dirs: list = field(default_factory=list)
    backtests: list = field(default_factory=list)
    navs: list = field(default_factory=list)
    factor_batches: list = field(default_factory=list)
    signals: list = field(default_factory=list)
    markdowns: list = field(default_factory=list)


def _csv_columns(path):
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline().strip()
    return [c.strip() for c in header.split(",") if c.strip() and c.strip() != "date"]


def scan_reports(root):
    cat = Catalog(root=root)
    if not root or not os.path.isdir(root):
        return cat
    for name in sorted(os.listdir(root), reverse=True):
        path = os.path.join(root, name)
        m = DIR_RE.match(name)
        if not m or not os.path.isdir(path):
            continue
        date, topic = m.groups()
        entries = sorted(os.listdir(path))
        rd = ReportDir(date, topic, path, markdowns=[os.path.join(path, e) for e in entries if e.lower().endswith(".md")])
        cat.dirs.append(rd)
        cat.markdowns.extend(rd.markdowns)
        orders = []
        for e in entries:
            p = os.path.join(path, e)
            if os.path.isdir(p) and e.endswith("_runs") and not e.startswith("tear_"):
                files = {k: (os.path.join(p, f) if os.path.exists(os.path.join(p, f)) else None) for k, f in RQ_FILES.items()}
                if any(files.values()):
                    cat.backtests.append(BacktestRun(date, topic, e[:-len("_runs")], p, files))
            elif os.path.isfile(p) and e.endswith("_navs.csv"):
                cat.navs.append(NavFile(date, topic, p, _csv_columns(p)))
            elif os.path.isfile(p) and e.startswith("orders_") and e.endswith(".csv"):
                orders.append(p)
        verdict = os.path.join(path, "factor_verdict.md")
        if os.path.exists(verdict):
            tear = {e[len("tear_"):-len("_runs")]: os.path.join(path, e) for e in entries
                    if e.startswith("tear_") and e.endswith("_runs") and os.path.isdir(os.path.join(path, e))}
            cat.factor_batches.append(FactorBatch(date, topic, path, verdict, tear))
        if topic.startswith(SIGNAL_PREFIX) and orders:
            log = os.path.join(path, "signal_log.md")
            cat.signals.append(SignalSet(date, topic[len(SIGNAL_PREFIX):], path, orders, log if os.path.exists(log) else None))
    return cat
