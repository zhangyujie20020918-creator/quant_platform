# coding: utf-8
"""RQAlpha 可插拔 store 的实现:每个 store 从我们 store 的一张表供数,格式与 ricequant bundle 一致。

对应关系(卡3 阶段B 任务卡表):
    StoreCalendarStore      ← core.calendar(文件模式;来源 trade_cal)。拒绝周内近似。
    InstrumentTable         ← stock_basic(含退市)+ index_daily(指数首日)。
    StoreDayBarStore        ← stock_daily(CS,9 字段含涨跌停)/ index_daily(INDX,7 字段)。原始价,不复权。
    StoreAdjFactorStore     ← adj_factor:两种视图
        ex_cum_factors():   (start_date, ex_cum_factor),RQAlpha history_bars 前/后复权用;
        split_factors():    因子变动日的比值当作"拆股",RQAlpha 持仓过除权日按比例调股数/成本。
                            分红不单独给(置空),否则与因子重复计——总回报口径 = 自研 hfq。
    StoreSuspendedDateSet   ← 推导:交易日 ∧ 在 [首个bar, 数据末日] 内 ∧ 无行 → 停牌(口径书面声明)。
    StoreSTDateSet          ← namechange:名称匹配 ^S?\\*?ST 的区间。
数值规则(涨跌停幅/整手/T+1)一律查品种规则表 instruments.cn_stock,本文件不出现数字。
"""
import datetime as _dt
import re

import numpy as np
import pandas as pd
from rqalpha.const import MARKET
from rqalpha.data.base_data_source.storage_interface import (AbstractCalendarStore, AbstractDateSet,
                                                             AbstractDayBarStore, AbstractSimpleFactorStore)
from rqalpha.model.instrument import Instrument
from rqalpha.utils.risk_free_helper import YIELD_CURVE_TENORS

from backtest.rqalpha_adapter.symbols import to_order_book_id, to_symbol
from core.calendar import TradingCalendar
from core.config import get
from data import store
from instruments.cn_stock import board_type, price_limit_ratios, round_lot

CS_DTYPE = np.dtype([("datetime", "<i8"), ("open", "<f8"), ("close", "<f8"), ("high", "<f8"), ("low", "<f8"),
                     ("volume", "<f8"), ("total_turnover", "<f8"), ("limit_up", "<f8"), ("limit_down", "<f8")])
INDX_DTYPE = np.dtype([("datetime", "<i8"), ("open", "<f8"), ("close", "<f8"), ("high", "<f8"), ("low", "<f8"),
                       ("volume", "<f8"), ("total_turnover", "<f8")])
EX_CUM_DTYPE = np.dtype([("start_date", "<i8"), ("ex_cum_factor", "<f8")])
SPLIT_DTYPE = np.dtype([("ex_date", "<i8"), ("split_factor", "<f8")])

_FAR_FUTURE = 99991231


# ---------- 日期整数(RQAlpha 约定:bar 用 YYYYMMDD000000,DateSet 用 YYYYMMDD) ----------

def date_int(d):
    """任意日期表示 → int YYYYMMDD。接受 date/datetime/Timestamp/字符串/int(YYYYMMDD 或 YYYYMMDDHHMMSS)。"""
    if isinstance(d, (int, np.integer)):
        d = int(d)
        return d // 1000000 if d > 99999999 else d
    if isinstance(d, (_dt.date, _dt.datetime, pd.Timestamp)):
        return d.year * 10000 + d.month * 100 + d.day
    return date_int(pd.Timestamp(d))


def dates_to_bar_int(dates):
    """DatetimeIndex/Series → int64 数组 YYYYMMDD000000。"""
    idx = pd.DatetimeIndex(dates)
    return (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy().astype("int64") * 1000000


def _round_half_up_2(x):
    """交易所涨跌停价四舍五入到 0.01(np.round 是银行家舍入,不用)。"""
    return np.floor(np.asarray(x, dtype=float) * 100 + 0.5) / 100


# ---------- 日历 ----------

class StoreCalendarStore(AbstractCalendarStore):
    def __init__(self, days):
        self._days = pd.DatetimeIndex(pd.to_datetime(list(days))).normalize()

    @classmethod
    def load(cls, cfg, root=None):
        cal = TradingCalendar.load(cfg, root=root)
        if cal.source != "file":
            raise RuntimeError("交易日历不是文件模式(source=%s):回测拒绝周内近似,先跑 "
                               "`python -m data.fetch --tables trade_cal` 导出日历" % cal.source)
        return cls(cal.trading_days("1900-01-01", "2199-12-31"))

    def get_trading_calendar(self):
        return self._days


# ---------- instruments ----------

class InstrumentTable:
    """stock_basic(含退市)→ RQAlpha Instrument(CS);index_daily 出现过的指数 → INDX。"""
    _STATUS = {"L": "Active", "D": "Delisted", "P": "TemporarySuspended"}

    def __init__(self, basic, index_first_dates, cfg):
        self._cfg = cfg
        self._board, self._listed, self._instruments = {}, {}, []
        tplus = int(get(cfg, "instruments.cn_stock.market_tplus"))
        for row in basic.itertuples(index=False):
            board = board_type(row.market)
            obid = to_order_book_id(row.symbol)
            listed = None if pd.isna(row.list_date) else pd.Timestamp(row.list_date).to_pydatetime()
            delisted = None if pd.isna(row.delist_date) else pd.Timestamp(row.delist_date).to_pydatetime()
            self._board[row.symbol] = board
            self._listed[row.symbol] = listed
            self._instruments.append(Instrument({
                "order_book_id": obid, "symbol": row.name or row.symbol, "type": "CS",
                "exchange": obid.partition(".")[2], "trading_code": obid.partition(".")[0],
                "listed_date": listed, "de_listed_date": delisted,
                "round_lot": round_lot(board, cfg), "board_type": board,
                "status": self._STATUS.get(row.list_status, "Unknown"), "special_type": "Normal",
                "market_tplus": tplus,
            }, market=MARKET.CN))
        for sym, first in sorted(index_first_dates.items()):
            obid = to_order_book_id(sym)
            self._instruments.append(Instrument({
                "order_book_id": obid, "symbol": sym, "type": "INDX", "exchange": "",
                "listed_date": pd.Timestamp(first).to_pydatetime(), "de_listed_date": None,
                "round_lot": 1, "market_tplus": 0, "status": "Active",
            }, market=MARKET.CN))

    @classmethod
    def load(cls, cfg, root=None):
        basic = store.read_table("stock_basic", root=root, cfg=cfg)
        idx = store.read_table("index_daily", columns=["date", "symbol"], root=root, cfg=cfg)
        first = idx.groupby("symbol")["date"].min().to_dict() if len(idx) else {}
        return cls(basic, first, cfg)

    def instruments(self):
        return list(self._instruments)

    def board(self, symbol):
        return self._board.get(symbol)

    def listed_date(self, symbol):
        return self._listed.get(symbol)


# ---------- ST ----------

class StoreSTDateSet(AbstractDateSet):
    """namechange 里名称匹配 ST 前缀(ST/*ST/SST/S*ST)的区间 → 该日是否 ST。"""
    ST_PATTERN = re.compile(r"^S?\*?ST", re.IGNORECASE)

    def __init__(self, namechange):
        self._symbols = set(namechange["symbol"]) if len(namechange) else set()
        self._intervals = {}
        if len(namechange):
            st = namechange[namechange["name"].fillna("").str.strip().str.match(self.ST_PATTERN)]
            for sym, g in st.groupby("symbol"):
                starts = np.array([date_int(d) for d in g["start_date"]], dtype="int64")
                ends = np.array([_FAR_FUTURE if pd.isna(d) else date_int(d) for d in g["end_date"]], dtype="int64")
                self._intervals[sym] = (starts, ends)

    @classmethod
    def load(cls, cfg, root=None):
        return cls(store.read_table("namechange", root=root, cfg=cfg))

    def _flags_int(self, symbol, ints):
        iv = self._intervals.get(symbol)
        if iv is None:
            return np.zeros(len(ints), dtype=bool)
        starts, ends = iv
        d = np.asarray(ints, dtype="int64")[:, None]
        return ((d >= starts[None, :]) & (d <= ends[None, :])).any(axis=1)

    def flags(self, symbol, dates):
        """向量化:symbol 在 dates(DatetimeIndex)各日是否 ST(供 bar 层算涨跌停)。"""
        idx = pd.DatetimeIndex(dates)
        return self._flags_int(symbol, (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy())

    def contains(self, order_book_id, dates):
        symbol = to_symbol(order_book_id)
        if symbol not in self._symbols:
            return None
        return self._flags_int(symbol, [date_int(d) for d in dates]).tolist()


# ---------- 日线 bar ----------

def _stock_limit_fn(cfg, st, table):
    """涨跌停价 = 昨收 × (1 ± 幅度),幅度查品种规则表(板块/ST/日期);上市首日无涨跌停 → NaN。"""
    def fn(symbol, df):
        dates = pd.DatetimeIndex(df["date"])
        board = table.board(symbol) or board_type(None)
        ratios = price_limit_ratios(board, dates, st.flags(symbol, dates), cfg)
        pre = df["pre_close"].to_numpy(dtype=float)
        up, down = _round_half_up_2(pre * (1 + ratios)), _round_half_up_2(pre * (1 - ratios))
        listed = table.listed_date(symbol)
        if listed is not None:
            first_day = np.asarray(dates == pd.Timestamp(listed))
            up[first_day], down[first_day] = np.nan, np.nan
        return up, down
    return fn


class StoreDayBarStore(AbstractDayBarStore):
    """从一张日线表供 RQAlpha 日线 bar(原始价);按标的懒加载,可 preload 批量预载(一次下推读取)。"""

    def __init__(self, table, dtype, cfg, root=None, limit_fn=None):
        self._table, self._dtype, self._cfg, self._root, self._limit_fn = table, dtype, cfg, root, limit_fn
        self._cache = {}

    @classmethod
    def for_stocks(cls, cfg, root=None, st=None, table=None):
        st = st or StoreSTDateSet.load(cfg, root)
        table = table or InstrumentTable.load(cfg, root)
        return cls("stock_daily", CS_DTYPE, cfg, root, limit_fn=_stock_limit_fn(cfg, st, table))

    @classmethod
    def for_indexes(cls, cfg, root=None):
        return cls("index_daily", INDX_DTYPE, cfg, root)

    def _to_bars(self, symbol, df):
        df = df.sort_values("date").reset_index(drop=True)
        arr = np.empty(len(df), dtype=self._dtype)
        arr["datetime"] = dates_to_bar_int(df["date"])
        for f in ("open", "close", "high", "low", "volume"):
            arr[f] = df[f].to_numpy(dtype=float)
        arr["total_turnover"] = df["amount"].to_numpy(dtype=float)
        if "limit_up" in self._dtype.names:
            up, down = self._limit_fn(symbol, df)
            arr["limit_up"], arr["limit_down"] = up, down
        return arr

    def preload(self, order_book_ids):
        """一次读取多只标的(下推过滤),避免逐只全表扫描。未在表里的标的记为空。"""
        obids = [o for o in order_book_ids if o not in self._cache]
        if not obids:
            return
        symbols = [to_symbol(o) for o in obids]
        df = store.read_table(self._table, symbols=symbols, root=self._root, cfg=self._cfg)
        for sym, g in df.groupby("symbol"):
            self._cache[to_order_book_id(sym)] = self._to_bars(sym, g)
        for o in obids:
            self._cache.setdefault(o, np.empty(0, dtype=self._dtype))

    def get_bars(self, order_book_id):
        if order_book_id not in self._cache:
            self.preload([order_book_id])
        return self._cache[order_book_id]

    def get_date_range(self, order_book_id):
        bars = self.get_bars(order_book_id)
        if len(bars) == 0:
            return 0, 0
        return int(bars["datetime"][0]), int(bars["datetime"][-1])


# ---------- 复权因子 ----------

class StoreAdjFactorStore:
    """adj_factor 表 → 因子变动事件 [(日期, 因子)](首条为区间首日);派生两种 RQAlpha 视图。"""

    def __init__(self, cfg, root=None):
        self._cfg, self._root = cfg, root
        self._events = {}

    def preload(self, order_book_ids):
        obids = [o for o in order_book_ids if o not in self._events]
        if not obids:
            return
        df = store.read_table("adj_factor", symbols=[to_symbol(o) for o in obids], root=self._root, cfg=self._cfg)
        for sym, g in df.groupby("symbol"):
            g = g.sort_values("date")
            f = g["adj_factor"].to_numpy(dtype=float)
            change = np.r_[True, ~np.isclose(f[1:], f[:-1], rtol=1e-9, atol=0.0)]
            self._events[to_order_book_id(sym)] = (dates_to_bar_int(g["date"])[change], f[change])
        for o in obids:
            self._events.setdefault(o, None)

    def events(self, order_book_id):
        if order_book_id not in self._events:
            self.preload([order_book_id])
        return self._events[order_book_id]

    def ex_cum_factors(self):
        return _ExCumFactorView(self)

    def split_factors(self):
        return _SplitFactorView(self)


class _ExCumFactorView(AbstractSimpleFactorStore):
    """(start_date, ex_cum_factor):首条 start_date=0 表示"首次记录之前沿用首值"(见 data_source 的 get_ex_cum_factor)。"""

    def __init__(self, parent):
        self._parent = parent

    def get_factors(self, order_book_id):
        ev = self._parent.events(order_book_id)
        if ev is None:
            return None
        dates, factors = ev
        out = np.empty(len(dates), dtype=EX_CUM_DTYPE)
        out["start_date"] = dates
        out["start_date"][0] = 0
        out["ex_cum_factor"] = factors
        return out


class _SplitFactorView(AbstractSimpleFactorStore):
    """(ex_date, split_factor):因子变动日的比值 f_t / f_{t-1};无变动 → None。"""

    def __init__(self, parent):
        self._parent = parent

    def get_factors(self, order_book_id):
        ev = self._parent.events(order_book_id)
        if ev is None or len(ev[0]) < 2:
            return None
        dates, factors = ev
        out = np.empty(len(dates) - 1, dtype=SPLIT_DTYPE)
        out["ex_date"] = dates[1:]
        out["split_factor"] = factors[1:] / factors[:-1]
        return out


# ---------- 停牌 ----------

class StoreSuspendedDateSet(AbstractDateSet):
    """停牌口径(书面声明):日线表缺行即视为停牌——限定在交易日、且在 [该股首个 bar, 数据末日] 内。
    上市前/数据末日后不算停牌;表里完全没有的标的返回 None(RQAlpha 约定 = 不知道 = 不停牌)。"""

    def __init__(self, bar_store, trading_days, data_end):
        self._bars = bar_store
        idx = pd.DatetimeIndex(trading_days)
        self._cal = set((idx.year * 10000 + idx.month * 100 + idx.day).tolist())
        self._end = date_int(data_end)
        self._have = {}

    def contains(self, order_book_id, dates):
        if order_book_id not in self._have:
            bars = self._bars.get_bars(order_book_id)
            self._have[order_book_id] = set((bars["datetime"] // 1000000).tolist()) if len(bars) else None
        have = self._have[order_book_id]
        if have is None:
            return None
        first = min(have)
        out = []
        for d in dates:
            di = date_int(d)
            out.append(di in self._cal and first <= di <= self._end and di not in have)
        return out


# ---------- 无风险利率(我们没有收益率曲线表,用 config 常数) ----------

class ConstantYieldCurve:
    """常数利率曲线。RQAlpha DataProxy.get_risk_free_rate 用 `if rate and ...` 判缺失,利率 0 会被当作缺失
    → 报表 sharpe/alpha 全 NaN;故 0 一律给一个数值上等于 0 的极小正数(EPS),不改变任何指标。"""
    EPS = 1e-12

    def __init__(self, rate):
        self._rate = float(rate) if float(rate) != 0.0 else self.EPS

    def get_yield_curve(self, start_date, end_date, tenor=None):
        cols = list(YIELD_CURVE_TENORS.values())
        df = pd.DataFrame([[self._rate] * len(cols)], index=[pd.Timestamp(start_date)], columns=cols)
        return df[list(tenor)] if tenor else df
