# coding: utf-8
"""AKShare 备源(原则1"来源不写死"的对冲落点)。

角色定位:主源(Tushare)失效或有缺口时的备份/修补,**不覆盖口径敏感的表**——
adj_factor(各源复权基准不同,混用会算错复权价)、namechange、index_weight
(akshare 只给当前成分,不能当历史 PIT 快照)一律不接,由 store 的来源优先级保证
主源赢、备源只补主源没有的行。

其历史接口按标的(不是按交易日),故 stock_daily 只用于修补 config
data.symbols.stock_patch 指定的清单;指数/ETF 用 config 的固定清单,是真备份。
单位:akshare 成交量=手(→×100 股),成交额=元(不变)。symbol 用 6 位无后缀。
"""
import logging
import time

import pandas as pd

from core.config import get
from data.fetchers.base import Source
from data.schema import get_spec

log = logging.getLogger(__name__)

# akshare 底层打 eastmoney/sina,端点会间歇性断连;这类瞬断重试几乎必然恢复(旧项目同一经验结论)
_TRANSIENT = (ConnectionError, TimeoutError, OSError)

_SUPPORTED = {"trade_cal", "stock_basic", "stock_daily", "index_daily", "fund_daily"}
_DAILY_COLS = ["date", "symbol", "open", "high", "low", "close", "pre_close", "volume", "amount"]


def _bare(symbol):
    """'600000.SH' -> '600000'(akshare 用无后缀 6 位)。"""
    return symbol.split(".")[0]


class AksharesSource(Source):
    name = "akshare"

    def __init__(self, cfg, ak=None, root=None, max_retries=None, backoff=None):
        self.cfg, self.root = cfg, root
        f = get(cfg, "data.fetch", {}) or {}
        self.max_retries = max_retries if max_retries is not None else f.get("max_retries", 4)
        self.backoff = backoff if backoff is not None else f.get("backoff_sec", 2.0)
        if ak is None:
            import akshare as ak                      # 延迟 import:仅备源真被调用时才需要
        self.ak = ak

    def _call(self, method, **kwargs):
        """带瞬断重试的 akshare 调用(其端点不稳,单纯重试即可恢复)。"""
        attempt = 0
        while True:
            attempt += 1
            try:
                return getattr(self.ak, method)(**kwargs)
            except _TRANSIENT as e:
                if attempt >= self.max_retries:
                    raise
                log.warning("akshare %s 第%d次瞬断(%s),%.0fs后重试", method, attempt, e, self.backoff * attempt)
                time.sleep(self.backoff * attempt)

    def supports(self, table):
        return table in _SUPPORTED

    def plan(self, table, start, end):
        if table == "trade_cal":
            return ["%s_%s" % (pd.Timestamp(start).date(), pd.Timestamp(end).date())]
        if table == "stock_basic":
            return ["all"]
        if table == "stock_daily":
            return list(get(self.cfg, "data.symbols.stock_patch", []))
        if table == "index_daily":
            return list(get(self.cfg, "data.symbols.index"))
        if table == "fund_daily":
            return list(get(self.cfg, "data.symbols.etf"))
        raise KeyError("akshare 不支持表 %r" % table)

    def is_open_chunk(self, table, chunk):
        return True    # 备源按标的整段拉,始终视为未封口(主源优先级保证不覆盖主源数据)

    def fetch(self, table, chunk):
        return getattr(self, "_fetch_" + table)(chunk)

    # ---------- 各表 ----------

    def _empty_daily(self):
        return pd.DataFrame(columns=_DAILY_COLS)

    def _map_daily(self, raw, symbol):
        if raw is None or raw.empty:
            return self._empty_daily()
        df = raw.rename(columns={"日期": "date", "开盘": "open", "最高": "high", "最低": "low",
                                 "收盘": "close", "成交量": "volume", "成交额": "amount"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d")
        df["symbol"] = symbol
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce") * 100.0   # 手→股
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")           # 已是元
        df = df.sort_values("date")
        df["pre_close"] = pd.to_numeric(df["close"], errors="coerce").shift(1)
        keep = [c for c in _DAILY_COLS if c in df.columns]
        return df[keep].reset_index(drop=True)

    def _fetch_stock_daily(self, symbol):
        start = pd.Timestamp(get(self.cfg, "data.backfill_start", "2010-01-01")).strftime("%Y%m%d")
        raw = self._call("stock_zh_a_hist", symbol=_bare(symbol), period="daily", start_date=start,
                          end_date="20991231", adjust="")
        return self._map_daily(raw, symbol)

    def _fetch_index_daily(self, symbol):
        raw = self._call("stock_zh_index_daily_em", symbol=_bare(symbol))
        return self._map_daily(raw, symbol)

    def _fetch_fund_daily(self, symbol):
        start = pd.Timestamp(get(self.cfg, "data.backfill_start", "2010-01-01")).strftime("%Y%m%d")
        raw = self._call("fund_etf_hist_em", symbol=_bare(symbol), period="daily", start_date=start,
                           end_date="20991231", adjust="")
        return self._map_daily(raw, symbol)

    def _fetch_trade_cal(self, chunk):
        raw = self._call("tool_trade_date_hist_sina")
        if raw is None or raw.empty:
            return pd.DataFrame(columns=list(get_spec("trade_cal").columns))
        df = pd.DataFrame({"date": pd.to_datetime(raw["trade_date"]).dt.strftime("%Y%m%d")})
        df["exchange"] = get(self.cfg, "calendar.exchange", "SSE")
        df["is_open"] = 1
        return df

    def _fetch_stock_basic(self, _chunk):
        raw = self._call("stock_info_a_code_name")
        if raw is None or raw.empty:
            return pd.DataFrame(columns=list(get_spec("stock_basic").columns))
        df = pd.DataFrame({"symbol": raw["code"].astype(str), "name": raw["name"].astype(str)})
        df["exchange"] = None
        df["market"] = None
        df["list_status"] = "L"        # akshare 该接口只给在市股,退市/暂停用主源
        df["list_date"] = None
        df["delist_date"] = None
        return df
