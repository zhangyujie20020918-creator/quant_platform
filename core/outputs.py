# coding: utf-8
"""报告路径服务:全平台产出的唯一落点(旧项目"报告路径硬编码×6"之债的根治)。

约定:
- 人读的报告(md/结论):reports/{YYYY-MM-DD}_{topic}/          —— 默认入git
- 程序run产出(csv/parquet/图):reports/{YYYY-MM-DD}_{topic}/{name}_runs/
  —— 统一 *_runs/ 后缀,.gitignore 一条规则排除
- 日期默认今天;续写历史主题时显式传原日期,禁止在任何脚本里手拼 reports 路径。
"""
import datetime as _dt
import os
import re

from core.config import ROOT, get

_SAFE_NAME = re.compile(r"^[\w一-鿿.-]+$")


def _safe(name, what):
    name = str(name).strip().replace(" ", "_")
    if not name or not _SAFE_NAME.match(name):
        raise ValueError("%s 含非法字符(只允许中英文/数字/_/./-): %r" % (what, name))
    return name


def reports_root(cfg=None, root=None):
    root = root or ROOT
    rel = get(cfg or {}, "meta.reports_dir", "reports")
    return rel if os.path.isabs(rel) else os.path.join(root, rel)


def report_dir(topic, date=None, cfg=None, root=None):
    """reports/{date}_{topic}/,不存在则创建,返回绝对路径。"""
    date = str(date or _dt.date.today().isoformat())
    path = os.path.join(reports_root(cfg, root), "%s_%s" % (date, _safe(topic, "topic")))
    os.makedirs(path, exist_ok=True)
    return path


def run_dir(topic, name, date=None, cfg=None, root=None):
    """reports/{date}_{topic}/{name}_runs/(git排除的run产出目录),返回绝对路径。"""
    path = os.path.join(report_dir(topic, date, cfg, root), "%s_runs" % _safe(name, "name"))
    os.makedirs(path, exist_ok=True)
    return path
