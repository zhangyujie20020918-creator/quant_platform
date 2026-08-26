# coding: utf-8
"""交易日历:全平台唯一权威(旧项目 rebalance_dates 重复实现×2 之债的合并落点)。

两级来源:
1. 文件模式(source="file"):cache/calendar/trading_days.csv(卡1的fetcher落盘,
   单列日期),路径来自 config calendar.file,不写死。
2. 兜底模式(source="weekday_approx"):文件不存在时退化为"周一~周五"近似——
   **不含中国节假日**,加载时打WARNING,仅供开发期空管道运行;S1数据体检与出信号
   环节必须拒绝该模式(检查 calendar.source)。

调仓日历 rebalance_dates 的频率是参数(monthly_first/weekly_first),不写死,
新频率按需扩展。
"""
import logging
import os

import pandas as pd

log = logging.getLogger(__name__)


class TradingCalendar:
    def __init__(self, days=None, source="weekday_approx"):
        self.source = source
        if days is not None:
            idx = pd.DatetimeIndex(pd.to_datetime(list(days))).normalize()
            self._days = idx.sort_values().unique()
        else:
            self._days = None

    # ---------- 构造 ----------

    @classmethod
    def load(cls, cfg=None, root=None):
        """按 config calendar.file 加载;文件缺失时退化为周内近似(带WARNING)。"""
        from core.config import ROOT, get
        root = root or ROOT
        rel = get(cfg or {}, "calendar.file", "cache/calendar/trading_days.csv")
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if os.path.exists(path):
            df = pd.read_csv(path)
            return cls(days=pd.to_datetime(df.iloc[:, 0]), source="file")
        log.warning("交易日历文件不存在(%s),退化为周一~周五近似:不含节假日,"
                    "不可用于数据体检放行或出信号", path)
        return cls(source="weekday_approx")

    # ---------- 查询 ----------

    def is_trading_day(self, d):
        d = pd.Timestamp(d).normalize()
        if self.source == "file":
            return d in self._days
        return d.weekday() < 5

    def trading_days(self, start, end):
        """[start, end] 闭区间内的交易日 DatetimeIndex(升序)。"""
        start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
        if self.source == "file":
            return self._days[(self._days >= start) & (self._days <= end)]
        return pd.bdate_range(start, end)

    def next_trading_day(self, d, n=1):
        """d 之后第 n 个交易日(不含 d 本身)。"""
        return self._step(d, n)

    def prev_trading_day(self, d, n=1):
        """d 之前第 n 个交易日(不含 d 本身)。"""
        return self._step(d, -n)

    def _step(self, d, n):
        d = pd.Timestamp(d).normalize()
        if n == 0:
            raise ValueError("n 不能为 0(next/prev 均不含当日)")
        if self.source == "file":
            if n > 0:
                pos = self._days.searchsorted(d, side="right")
                target = pos + n - 1
            else:
                pos = self._days.searchsorted(d, side="left")
                target = pos + n
            if not 0 <= target < len(self._days):
                raise IndexError("日历文件范围不足:%s 之外第 %d 个交易日越界" % (d.date(), n))
            return self._days[target]
        step = 1 if n > 0 else -1
        remaining, cur = abs(n), d
        while remaining:
            cur += pd.Timedelta(days=step)
            if cur.weekday() < 5:
                remaining -= 1
        return cur

    def rebalance_dates(self, start, end, freq="monthly_first"):
        """通用调仓日历。freq:monthly_first=每月第一个交易日;weekly_first=每周第一个交易日。
        新频率按需在此扩展,禁止各策略自行实现调仓日逻辑。"""
        days = self.trading_days(start, end)
        if len(days) == 0:
            return days
        s = days.to_series()
        if freq == "monthly_first":
            firsts = s.groupby(days.to_period("M")).first()
        elif freq == "weekly_first":
            firsts = s.groupby(days.to_period("W")).first()
        else:
            raise ValueError("未知调仓频率: %r(在 core/calendar.py 扩展,不要在策略层自实现)" % freq)
        return pd.DatetimeIndex(firsts.values)
