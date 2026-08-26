# coding: utf-8
"""Tushare 主源:直连(或经第三方代理)Tushare Pro HTTP 协议。

协议(与官方 tushare 包一致,故不依赖该包):POST JSON {"api_name","token","params","fields"} 到 base_url,
响应 {"code":0,"data":{"fields":[...],"items":[[...]]}}。旧项目实测代理只是镜像了此协议。

单位换算在此处完成(Tushare:vol=手、amount=千元 → 平台:volume=股、amount=元)。
分片策略:日频大表按交易日分片(封口,断点续传);按标的/按年的分片含今天则视为未封口每次重拉。
"""
import datetime as _dt
import logging
import time

import pandas as pd
import requests

from core.calendar import TradingCalendar
from core.config import get
from data.fetchers.base import Source, SourceUnavailable
from data.schema import get_spec

log = logging.getLogger(__name__)


class TushareError(RuntimeError):
    pass


_AUTH_CODES = {2002}
_RATE_LIMIT_KEYWORDS = ("每分钟", "每小时", "每天", "频率", "频繁", "limit")


class TushareHTTP:
    def __init__(self, token, base_url, session=None, rate_sleep=0.2, timeout=30,
                 max_retries=4, backoff=2.0, rate_limit_sleep=20):
        self.token, self.base_url = token, base_url
        self.session = session or requests.Session()
        self.rate_sleep, self.timeout = rate_sleep, timeout
        self.max_retries, self.backoff, self.rate_limit_sleep = max_retries, backoff, rate_limit_sleep

    def query(self, api_name, fields=None, **params):
        payload = {"api_name": api_name, "token": self.token, "params": params, "fields": fields or ""}
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self.session.post(self.base_url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                body = resp.json()
            except Exception as e:                      # 网络/HTTP/JSON 层:指数退避重试
                if attempt >= self.max_retries:
                    raise
                log.warning("tushare %s 第%d次失败(%s),%.0fs后重试", api_name, attempt, e, self.backoff * attempt)
                time.sleep(self.backoff * attempt)
                continue
            code = body.get("code", -1)
            if code == 0:
                data = body.get("data") or {}
                df = pd.DataFrame(data.get("items") or [], columns=data.get("fields") or None)
                if self.rate_sleep:
                    time.sleep(self.rate_sleep)
                return df
            msg = str(body.get("msg", ""))
            if code in _AUTH_CODES or "token" in msg.lower():
                raise SourceUnavailable("tushare 鉴权失败: code=%s msg=%s" % (code, msg))
            if any(k in msg for k in _RATE_LIMIT_KEYWORDS):
                if attempt >= self.max_retries:
                    raise TushareError("tushare 限速重试耗尽: %s" % msg)
                log.warning("tushare %s 触发限速(%s),等待 %ss", api_name, msg, self.rate_limit_sleep)
                time.sleep(self.rate_limit_sleep)
                continue
            raise TushareError("tushare 接口错误: code=%s msg=%s(api=%s params=%s)" % (code, msg, api_name, params))


def _ymd(d):
    return pd.Timestamp(d).strftime("%Y%m%d")


def _years(start, end):
    return list(range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1))


def _empty(table):
    return pd.DataFrame(columns=list(get_spec(table).columns))


def _finish(df, table, rename, volume_scale=100.0, amount_scale=1000.0):
    """重命名 + 单位换算 + 只保留 spec 列(缺列由 schema.validate 在写入时报错,不在此静默补)。"""
    if df is None or df.empty:
        return _empty(table)
    df = df.rename(columns=rename)
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce") * volume_scale
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce") * amount_scale
    keep = [c for c in get_spec(table).columns if c in df.columns]
    return df[keep].reset_index(drop=True)


_DAILY_RENAME = {"ts_code": "symbol", "trade_date": "date", "vol": "volume"}


class TushareSource(Source):
    name = "tushare"

    def __init__(self, cfg, http=None, root=None, page_limit=5000, today=None):
        self.cfg, self.root, self.page_limit = cfg, root, page_limit
        self.today = pd.Timestamp(today or _dt.date.today()).normalize()
        if http is None:
            cred = get(cfg, "credentials.tushare")
            f = get(cfg, "data.fetch", {}) or {}
            http = TushareHTTP(cred["token"], cred["base_url"],
                               rate_sleep=f.get("rate_sleep_sec", 0.2), timeout=f.get("timeout_sec", 30),
                               max_retries=f.get("max_retries", 4), backoff=f.get("backoff_sec", 2.0),
                               rate_limit_sleep=f.get("rate_limit_sleep_sec", 20))
        self.http = http
        self._cal = None

    # ---------- 接口 ----------

    def supports(self, table):
        return table in self._FETCHERS

    def plan(self, table, start, end):
        if table == "trade_cal":
            return ["%s_%s" % (_ymd(start), _ymd(end))]
        if table == "stock_basic":
            return ["L", "D", "P"]
        if table in ("stock_daily", "adj_factor"):
            return [d.strftime("%Y%m%d") for d in self._calendar().trading_days(start, end)]
        if table == "namechange":
            return ["all"]
        if table == "index_daily":
            return list(get(self.cfg, "data.symbols.index"))
        if table == "index_weight":
            return ["%s_%d" % (s, y) for s in get(self.cfg, "data.symbols.index_weight") for y in _years(start, end)]
        if table == "fund_daily":
            return ["%s_%d" % (s, y) for s in get(self.cfg, "data.symbols.etf") for y in _years(start, end)]
        raise KeyError("tushare 不支持表 %r" % table)

    def is_open_chunk(self, table, chunk):
        if table in ("stock_daily", "adj_factor"):
            return pd.Timestamp(chunk) >= self.today          # 今天的分片可能盘中不全
        if table in ("index_weight", "fund_daily"):
            return int(chunk.rpartition("_")[2]) >= self.today.year
        return True                                           # 整表刷新型:日历/基本信息/名称变更/指数全史

    def fetch(self, table, chunk):
        return self._FETCHERS[table](self, chunk)

    # ---------- 内部 ----------

    def _calendar(self):
        if self._cal is None:
            self._cal = TradingCalendar.load(self.cfg, root=self.root)
        return self._cal

    def _fetch_trade_cal(self, chunk):
        start, end = chunk.split("_")
        raw = self.http.query("trade_cal", fields="exchange,cal_date,is_open",
                              exchange=get(self.cfg, "calendar.exchange", "SSE"), start_date=start, end_date=end)
        return _finish(raw, "trade_cal", {"cal_date": "date"})

    def _fetch_stock_basic(self, chunk):
        raw = self.http.query("stock_basic", fields="ts_code,name,exchange,market,list_status,list_date,delist_date",
                              list_status=chunk)
        return _finish(raw, "stock_basic", {"ts_code": "symbol"})

    def _fetch_stock_daily(self, chunk):
        raw = self.http.query("daily", trade_date=chunk)
        return _finish(raw, "stock_daily", _DAILY_RENAME)

    def _fetch_adj_factor(self, chunk):
        raw = self.http.query("adj_factor", trade_date=chunk)
        return _finish(raw, "adj_factor", _DAILY_RENAME)

    def _fetch_namechange(self, _chunk):
        frames, offset = [], 0
        while True:
            page = self.http.query("namechange", fields="ts_code,name,start_date,end_date,change_reason",
                                   limit=self.page_limit, offset=offset)
            if page is None or page.empty:
                break
            frames.append(page)
            if len(page) < self.page_limit:
                break
            offset += self.page_limit
        if not frames:
            return _empty("namechange")
        df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["ts_code", "start_date"], keep="last")
        return _finish(df, "namechange", {"ts_code": "symbol"})

    def _fetch_index_daily(self, chunk):
        start = _ymd(get(self.cfg, "data.backfill_start", "19900101"))
        end, frames, page_limit = _ymd(self.today), [], 8000
        while True:   # 单次上限8000行:触顶则向前翻页
            page = self.http.query("index_daily", ts_code=chunk, start_date=start, end_date=end)
            if page is None or page.empty:
                break
            frames.append(page)
            if len(page) < page_limit:
                break
            end = (pd.to_datetime(page["trade_date"], format="%Y%m%d").min() - pd.Timedelta(days=1)).strftime("%Y%m%d")
            if end < start:
                break
        df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["ts_code", "trade_date"]) if frames else None
        return _finish(df, "index_daily", _DAILY_RENAME)

    def _fetch_index_weight(self, chunk):
        symbol, _, year = chunk.rpartition("_")
        frames = []
        for m in range(1, 13):    # 按月查,规避单次行数上限
            start = "%s%02d01" % (year, m)
            end = (pd.Timestamp(start) + pd.offsets.MonthEnd(0)).strftime("%Y%m%d")
            page = self.http.query("index_weight", index_code=symbol, start_date=start, end_date=end)
            if page is not None and not page.empty:
                frames.append(page)
        df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["index_code", "con_code", "trade_date"]) if frames else None
        return _finish(df, "index_weight", {"index_code": "index_symbol", "con_code": "symbol", "trade_date": "date"})

    def _fetch_fund_daily(self, chunk):
        symbol, _, year = chunk.rpartition("_")
        raw = self.http.query("fund_daily", ts_code=symbol, start_date="%s0101" % year, end_date="%s1231" % year)
        return _finish(raw, "fund_daily", _DAILY_RENAME)

    _FETCHERS = {
        "trade_cal": _fetch_trade_cal, "stock_basic": _fetch_stock_basic, "stock_daily": _fetch_stock_daily,
        "adj_factor": _fetch_adj_factor, "namechange": _fetch_namechange, "index_daily": _fetch_index_daily,
        "index_weight": _fetch_index_weight, "fund_daily": _fetch_fund_daily,
    }
