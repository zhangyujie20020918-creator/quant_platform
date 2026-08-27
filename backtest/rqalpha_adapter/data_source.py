# coding: utf-8
"""StoreDataSource:RQAlpha 完整数据源,只读我们的 store,不碰 ricequant bundle(卡3 阶段B)。

继承 BaseDataSource 是为了复用它的查询逻辑(history_bars 复权、get_bar、instruments 索引、
DateSet 分发),但**不调用其 __init__**——那里硬编码打开 14 个 bundle 文件。这里按它的注册表
结构自建,再把七个 store 注册进去(见 stores.py 头注的对应表)。

有意覆盖的行为:
- get_ex_cum_factor:基类按上市日过滤因子并强插 (0, 1.0)。我们的因子基准不是 1(Tushare 后复权
  基准),首值必须保留,否则 2010 以前上市的股票历史复权全部错位——重复/错位复权的头号陷阱。
- get_instruments(types=...):未注册的类型(ETF/期货等)返回空而非 KeyError。
- available_data_range:日历首日 → min(日历末日, stock_daily 末日)。
- 无收益率曲线/股份转换/期货信息:常数无风险利率(config)、None、NotImplementedError。
"""
from collections import ChainMap

from rqalpha.const import INSTRUMENT_TYPE, TRADING_CALENDAR_TYPE
from rqalpha.data.base_data_source.data_source import BaseDataSource
from rqalpha.utils.functools import lru_cache

from backtest.rqalpha_adapter.stores import (ConstantYieldCurve, InstrumentTable, StoreAdjFactorStore,
                                             StoreCalendarStore, StoreDayBarStore, StoreSTDateSet,
                                             StoreSuspendedDateSet)
from backtest.rqalpha_adapter.symbols import to_order_book_id
from core.config import get
from data import store


class StoreDataSource(BaseDataSource):
    def __init__(self, cfg, root=None, preload=None):   # noqa: 不调用 super().__init__,见头注
        self._cfg, self._root = cfg, root
        # --- BaseDataSource 的注册表结构(与其 __init__ 一致,只是不从 bundle 填充) ---
        self._future_info_store = None
        self._yield_curve = ConstantYieldCurve(get(cfg, "backtest.risk_free_rate", 0.0))
        self._share_transformation = None
        self._ins_id_or_sym_type_map = {}
        self._day_bar_stores, self._dividend_stores, self._split_stores = {}, {}, {}
        self._calendar_stores, self._ex_factor_stores = {}, {}
        self._id_instrument_map, self._sym_instrument_map = {}, {}
        self._id_or_sym_instrument_map = ChainMap(self._id_instrument_map, self._sym_instrument_map)
        self._grouped_instruments = {}

        # --- 我们的 store ---
        calendar = StoreCalendarStore.load(cfg, root)
        self.register_calendar_store(TRADING_CALENDAR_TYPE.CN_STOCK, calendar)
        self._table = InstrumentTable.load(cfg, root)
        self.register_instruments(self._table.instruments())
        self._st = StoreSTDateSet.load(cfg, root)
        self._st_stock_days = self._st
        self._cs_bars = StoreDayBarStore.for_stocks(cfg, root, st=self._st, table=self._table)
        self.register_day_bar_store(INSTRUMENT_TYPE.CS, self._cs_bars)
        self.register_day_bar_store(INSTRUMENT_TYPE.INDX, StoreDayBarStore.for_indexes(cfg, root))
        self._adj = StoreAdjFactorStore(cfg, root)
        self.register_ex_factor_store(INSTRUMENT_TYPE.CS, self._adj.ex_cum_factors())
        self.register_split_store(INSTRUMENT_TYPE.CS, self._adj.split_factors())
        # 分红 store 故意不注册:现金分红已体现在因子比值里(合成拆分),再给一次就是重复计。

        days = calendar.get_trading_calendar()
        _, data_end = store.date_range("stock_daily", root=root, cfg=cfg)
        end = days[-1] if data_end is None else min(days[-1], data_end)
        self._data_range = (days[0], end)
        self._suspend_days = [StoreSuspendedDateSet(self._cs_bars, days, end)]
        if preload:
            self.preload(preload)

    # ---------- 批量预载(平台 symbol 口径,如 universe.all_symbols()) ----------

    def preload(self, symbols):
        obids = [to_order_book_id(s) for s in symbols]
        self._cs_bars.preload(obids)
        self._adj.preload(obids)

    # ---------- 覆盖基类 ----------

    @lru_cache(1024)
    def get_ex_cum_factor(self, instrument):
        try:
            ex_store = self._ex_factor_stores[instrument.type, instrument.market]
        except KeyError:
            return None
        return ex_store.get_factors(instrument.order_book_id)

    def get_instruments(self, id_or_syms=None, types=None):
        if id_or_syms is None and types is not None:
            types = [t for t in types if t in self._grouped_instruments]
            if not types:
                return iter(())
        return super().get_instruments(id_or_syms, types)

    def available_data_range(self, frequency):
        s, e = self._data_range
        return s.date(), e.date()

    def get_share_transformation(self, order_book_id):
        return None

    def get_futures_trading_parameters(self, instrument, dt):
        raise NotImplementedError("store 数据源暂不含期货交易参数(品种未接入)")
