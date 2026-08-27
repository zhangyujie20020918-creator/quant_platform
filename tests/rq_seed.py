# coding: utf-8
"""RQAlpha 适配层测试共用的合成 store(不触网、不依赖真实缓存)。

小世界:2014-06-03~06-20 共 14 个交易日(06-02 端午休市)。
- 000001.SZ:06-12 除权(因子 58.387→71.054,昨收 11.78→9.68),06-16 停牌(无行)。
- 600000.SH:平价常数,因子常数 2.0(验证"无变动即无拆分")。
- 000005.SZ:06-10 起戴 ST(namechange),验证 ST 标记与 5% 涨跌停。
- 300001.SZ:创业板(改革前,10%);06-10 收盘触涨停(20→22)、06-13 收盘触跌停(20→18),验证涨停不可买/跌停不可卖。
- 600999.SH:2014-06-18 退市(bar 到 06-17),验证退市清算。999999.SZ:06-10 新上市(首日无涨跌停)。
- 688001.SH 科创板(区间外无行情)、000003.SZ 已退市(2002):只进 instruments。
- 指数 000300.SH / 000001.SH 日线;沪深300 成分快照 2014-05-30。
"""
import pandas as pd

from data import store
from data.fetch import export_calendar

TRADING_DAYS = pd.to_datetime([
    "2014-06-03", "2014-06-04", "2014-06-05", "2014-06-06", "2014-06-09", "2014-06-10", "2014-06-11",
    "2014-06-12", "2014-06-13", "2014-06-16", "2014-06-17", "2014-06-18", "2014-06-19", "2014-06-20"])
EX_DATE = pd.Timestamp("2014-06-12")
F_BEFORE, F_AFTER = 58.387, 71.054

RULES = {
    "round_lot": 100, "market_tplus": 1,
    "costs": {"commission_rate": 0.0002, "min_commission": 5.0,
              "stamp_tax_sell": [{"since": "2008-09-19", "rate": 0.001}, {"since": "2023-08-28", "rate": 0.0005}],
              "transfer_fee": [{"since": "2015-08-01", "rate": 0.00002}, {"since": "2022-04-29", "rate": 0.00001}]},
    "price_limit": {"default": 0.10, "st": 0.05},
    "boards": {"KSH": {"since": "2019-07-22", "price_limit": 0.20, "round_lot": 200},
               "GEM": {"since": "2020-08-24", "price_limit": 0.20},
               "BJS": {"since": "2020-07-27", "price_limit": 0.30}},
}


def make_cfg():
    return {
        "meta": {"cache_dir": "cache", "reports_dir": "reports"},
        "calendar": {"file": "cache/calendar/trading_days.csv", "exchange": "SSE"},
        "data": {"source_priority": ["tushare"]},
        "instruments": {"cn_stock": RULES},
        "backtest": {"risk_free_rate": 0.02},
    }


def _daily(symbol, dates, closes, pre_closes, opens=None):
    return pd.DataFrame({
        "date": dates, "symbol": symbol,
        "open": opens if opens is not None else closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "pre_close": pre_closes,
        "volume": 100_000_000.0, "amount": [c * 1_000_000.0 for c in closes]})   # 量给足,免触 RQAlpha 25% 成交量上限


def _write(root, name, df, chunk="all"):
    store.write_part(name, "tushare", chunk, df.assign(source="tushare"), root=root)
    store.consolidate(name, root=root)


def seed(root, cfg=None):
    cfg = cfg or make_cfg()
    days = TRADING_DAYS
    # 日历:交易日 + 两个休市日
    cal = pd.DataFrame({"date": list(days) + [pd.Timestamp("2014-06-02"), pd.Timestamp("2014-06-14")],
                        "exchange": "SSE", "is_open": [True] * len(days) + [False, False]})
    _write(root, "trade_cal", cal)
    export_calendar(cfg, root=root)

    basic = pd.DataFrame([
        ("000001.SZ", "平安银行", "SZSE", "主板", "L", "1991-04-03", None),
        ("600000.SH", "浦发银行", "SSE", "主板", "L", "1999-11-10", None),
        ("000005.SZ", "ST星源", "SZSE", "主板", "L", "1990-12-10", None),
        ("300001.SZ", "特锐德", "SZSE", "创业板", "L", "2009-10-30", None),
        ("999999.SZ", "新股", "SZSE", None, "L", "2014-06-10", None),
        ("688001.SH", "华兴源创", "SSE", "科创板", "L", "2019-07-22", None),
        ("000003.SZ", "PT金田A", "SZSE", "主板", "D", "1991-07-03", "2002-06-14"),
        ("600999.SH", "退市样本", "SSE", "主板", "D", "2005-01-04", "2014-06-18"),
    ], columns=["symbol", "name", "exchange", "market", "list_status", "list_date", "delist_date"])
    _write(root, "stock_basic", basic)

    # 000001:除权前 7 日 + 除权日起 6 日(06-16 停牌无行)
    d1 = [d for d in days if d != pd.Timestamp("2014-06-16")]
    c1 = [11.20, 11.30, 11.43, 11.38, 11.48, 11.75, 11.78, 9.71, 10.12, 10.20, 10.30, 10.40, 10.50]
    p1 = [11.10, 11.20, 11.30, 11.43, 11.38, 11.48, 11.75, 9.68, 9.71, 10.12, 10.20, 10.30, 10.40]
    o1 = [11.15, 11.25, 11.40, 11.40, 11.45, 11.70, 11.76, 9.62, 9.70, 10.15, 10.25, 10.35, 10.45]
    frames = [_daily("000001.SZ", d1, c1, p1, o1),
              _daily("600000.SH", days, [10.0] * 14, [10.0] * 14),
              _daily("000005.SZ", days, [3.0] * 14, [3.0] * 14),
              # 创业板:06-10 涨停收盘(昨收 20→22),06-13 跌停收盘(昨收 20→18)
              _daily("300001.SZ", days, [20.0] * 5 + [22.0, 22.0, 20.0, 18.0] + [18.0] * 5,
                     [20.0] * 5 + [20.0, 22.0, 22.0, 20.0] + [18.0] * 5,
                     [20.0] * 5 + [21.0, 22.0, 21.0, 19.0] + [18.0] * 5),
              _daily("600999.SH", days[:10], [5.0] * 10, [5.0] * 10),
              _daily("999999.SZ", days[5:], [7.2] * 9, [5.0] + [7.2] * 8)]
    _write(root, "stock_daily", pd.concat(frames, ignore_index=True))

    adj = pd.concat([
        pd.DataFrame({"date": d1, "symbol": "000001.SZ",
                      "adj_factor": [F_BEFORE if d < EX_DATE else F_AFTER for d in d1]}),
        pd.DataFrame({"date": days, "symbol": "600000.SH", "adj_factor": 2.0}),
        pd.DataFrame({"date": days, "symbol": "000005.SZ", "adj_factor": 1.0}),
        pd.DataFrame({"date": days, "symbol": "300001.SZ", "adj_factor": 1.0}),
        pd.DataFrame({"date": days[:10], "symbol": "600999.SH", "adj_factor": 1.0}),
        pd.DataFrame({"date": days[5:], "symbol": "999999.SZ", "adj_factor": 1.0}),
    ], ignore_index=True)
    _write(root, "adj_factor", adj)

    nc = pd.DataFrame([
        ("000005.SZ", "世纪星源", "2008-06-25", "2014-06-09", "撤销ST"),
        ("000005.SZ", "ST星源", "2014-06-10", None, "ST"),
        ("000001.SZ", "平安银行", "2012-08-02", None, "其他"),
    ], columns=["symbol", "name", "start_date", "end_date", "change_reason"])
    _write(root, "namechange", nc)

    idx = pd.concat([
        pd.DataFrame({"date": days, "symbol": "000300.SH", "open": 2100.0, "high": 2110.0, "low": 2090.0,
                      "close": [2100.0 + i for i in range(14)], "volume": 1e9, "amount": 1e11}),
        pd.DataFrame({"date": days, "symbol": "000001.SH", "open": 2000.0, "high": 2010.0, "low": 1990.0,
                      "close": [2000.0 + i for i in range(14)], "volume": 1e9, "amount": 1e11}),
    ], ignore_index=True)
    _write(root, "index_daily", idx)

    w = pd.DataFrame({"date": "2014-05-30", "index_symbol": "000300.SH",
                      "symbol": ["000001.SZ", "000005.SZ", "600000.SH"], "weight": [1.3, 0.5, 1.1]})
    _write(root, "index_weight", w)
    return cfg
