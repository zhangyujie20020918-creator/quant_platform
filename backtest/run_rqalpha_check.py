# coding: utf-8
"""卡3 阶段B 真实数据核对:RQAlpha 完全跑在我们的 store 上(无 bundle),逐项对账并出报告。

核对项(全部与我们 store / 自研价格层对账,不与 ricequant 对账):
 1. 数据源装配:instruments 数(含退市)、指数、日历范围、可用数据区间、构建耗时;
 2. 复权对账:RQAlpha history_bars 前复权 = backtest.prices qfq;后复权 = hfq(防重复/错位复权);
 3. 停牌/ST:真实停牌日与 ST 区间查询;
 4. 端到端回测:买入持有 000001 跨 2014-06-12 除权日——成交价 = store 原始收盘、股数按因子比例调整、
    市值连续、基准净值 = index_daily 累计收益;
 5. 预载性能:沪深300 历史全成分一次预载耗时。
用法:python -m backtest.run_rqalpha_check [--date 2026-08-27]
"""
from core.bootstrap import init  # noqa: F401  必须第一行(Windows 编码/日志统一入口)

import argparse
import datetime as dt
import os
import time
import warnings

import numpy as np
import pandas as pd
from rqalpha import run_func
from rqalpha.apis import order_shares
from rqalpha.const import INSTRUMENT_TYPE, TRADING_CALENDAR_TYPE

from backtest.prices import adjusted_panels
from backtest.rqalpha_adapter.data_source import StoreDataSource
from core.config import ROOT, load_config
from core.outputs import report_dir, run_dir
from data import store
from instruments.universe import IndexUniverse

warnings.filterwarnings("ignore", category=FutureWarning, module="rqalpha")   # RQAlpha 内部 pandas 弃用告警,与我们无关

TOPIC = "卡3阶段B"
SYM, OBID = "000001.SZ", "000001.XSHE"
EX_DATE = pd.Timestamp("2014-06-12")
BT_START, BT_END = "2014-06-04", "2014-06-30"
BENCH_SYM, BENCH_OBID = "000300.SH", "000300.XSHG"


class Checks:
    def __init__(self):
        self.rows = []

    def add(self, name, expected, observed, ok, note=""):
        self.rows.append({"项": name, "预期": expected, "实测": observed, "结果": "通过" if ok else "**不通过**", "说明": note})
        return ok

    def approx(self, name, expected, observed, rel=1e-9, note=""):
        ok = bool(np.isclose(expected, observed, rtol=rel, atol=0))
        return self.add(name, repr(expected), repr(observed), ok, note)

    def to_md(self):
        return pd.DataFrame(self.rows).to_markdown(index=False)

    @property
    def all_ok(self):
        return all(r["结果"] == "通过" for r in self.rows)


def check_assembly(cfg, ck, log):
    t0 = time.time()
    ds = StoreDataSource(cfg)
    build = time.time() - t0
    cs = list(ds.get_instruments(types=[INSTRUMENT_TYPE.CS]))
    basic = store.read_table("stock_basic")
    n_delisted = sum(1 for i in cs if i.status == "Delisted")
    ck.add("CS instruments 数 = stock_basic 行数", len(basic), len(cs), len(cs) == len(basic))
    ck.add("退市股进 instruments(防幸存者偏差)", int((basic["list_status"] == "D").sum()), n_delisted,
           n_delisted == int((basic["list_status"] == "D").sum()))
    indx = sorted(i.order_book_id for i in ds.get_instruments(types=[INSTRUMENT_TYPE.INDX]))
    ck.add("INDX instruments 来自 index_daily", "含 000300.XSHG", ", ".join(indx), BENCH_OBID in indx)
    cal = ds.get_trading_calendars()[TRADING_CALENDAR_TYPE.CN_STOCK]
    ck.add("日历 = core.calendar 文件模式", "2010-01-04 起", "%s→%s(%d 日)" % (cal[0].date(), cal[-1].date(), len(cal)),
           cal[0] == pd.Timestamp("2010-01-04"))
    s, e = ds.available_data_range("1d")
    dmin, dmax = store.date_range("stock_daily")
    ck.add("可用数据区间 = stock_daily 范围", "%s→%s" % (dmin.date(), dmax.date()), "%s→%s" % (s, e),
           s == dmin.date() and e == dmax.date())
    ck.add("数据源构建耗时(秒)", "<30", round(build, 2), build < 30, "含 stock_basic/namechange/index_daily 全读")
    log.info("数据源装配 %.2fs:CS=%d(退市 %d),INDX=%s", build, len(cs), n_delisted, indx)
    return ds


def check_adjust(ds, ck, log):
    ins = next(iter(ds.get_instruments(id_or_syms=[OBID])))
    at = EX_DATE.to_pydatetime()
    n = 8
    pre = ds.history_bars(ins, n, "1d", "close", at, adjust_type="pre", adjust_orig=at)
    post = ds.history_bars(ins, n, "1d", "close", at, adjust_type="post")
    raw = ds.history_bars(ins, n, "1d", "close", at, adjust_type="none")
    dates = [pd.Timestamp(str(int(d // 1000000))) for d in ds.history_bars(ins, n, "1d", "datetime", at, adjust_type="none")]
    _, qfq = adjusted_panels([SYM], dates[0], EX_DATE, method="qfq")
    _, hfq = adjusted_panels([SYM], dates[0], EX_DATE, method="hfq")
    ours_qfq = qfq[SYM].reindex(dates).to_numpy()
    ours_hfq = hfq[SYM].reindex(dates).to_numpy()
    ck.add("history_bars pre = backtest.prices qfq(除权日前后 %d 日)" % n,
           "max|diff|<1e-9", "%.2e" % np.max(np.abs(pre - ours_qfq)), np.allclose(pre, ours_qfq, rtol=0, atol=1e-9))
    ck.add("history_bars post = backtest.prices hfq",
           "max|diff|<1e-6", "%.2e" % np.max(np.abs(post - ours_hfq)), np.allclose(post, ours_hfq, rtol=0, atol=1e-6))
    daily = store.read_table("stock_daily", symbols=[SYM], start=dates[0], end=EX_DATE).sort_values("date")
    ck.add("history_bars none = store 原始收盘", "完全相等", "完全相等" if np.array_equal(raw, daily["close"].to_numpy()) else "不等",
           np.array_equal(raw, daily["close"].to_numpy()))
    # 除权日昨收:前复权后的 06-11 收盘应等于 Tushare 给的 06-12 pre_close(9.68),差异只在四舍五入
    pre_close_ex = float(daily[daily["date"] == EX_DATE]["pre_close"].iloc[0])
    ck.add("前复权 06-11 收盘 ≈ 除权日 pre_close", pre_close_ex, round(float(pre[-2]), 4), abs(pre[-2] - pre_close_ex) < 0.01,
           "Tushare pre_close 保留两位小数")
    sp = ds.get_split(ins)
    adj = store.read_table("adj_factor", symbols=[SYM], start="2014-06-01", end="2014-06-30").sort_values("date")
    f_before = float(adj[adj["date"] < EX_DATE]["adj_factor"].iloc[-1])
    f_after = float(adj[adj["date"] == EX_DATE]["adj_factor"].iloc[0])
    ratio = f_after / f_before
    on_ex = sp[sp["ex_date"] == int(EX_DATE.strftime("%Y%m%d")) * 1000000]
    ck.approx("合成 split 比值 = 因子比 f(06-12)/f(06-11)", ratio, float(on_ex["split_factor"][0]) if len(on_ex) else np.nan)
    ck.add("不单独供分红(防重复计)", "None", repr(ds.get_dividend(ins)), ds.get_dividend(ins) is None)
    log.info("复权对账通过:pre/post/none 三口径与自研价格层一致;split 比值 %.6f", ratio)
    return ratio


def check_flags(ds, ck, log):
    # 停牌:从 stock_daily 找 000001 在 2014 年缺的交易日(真实停牌),核对 is_suspended
    cal = ds.get_trading_calendars()[TRADING_CALENDAR_TYPE.CN_STOCK]
    days = cal[(cal >= "2014-01-01") & (cal <= "2014-12-31")]
    have = set(store.read_table("stock_daily", symbols=[SYM], start="2014-01-01", end="2014-12-31")["date"])
    missing = [d for d in days if d not in have]
    if missing:
        d = missing[0]
        flags = ds.is_suspended(OBID, [d.to_pydatetime(), (d - pd.Timedelta(days=1)).to_pydatetime()])
        ck.add("停牌推导:2014 年 000001 缺行日 %s" % d.date(), "[True, ?]", repr(flags), flags[0] is True,
               "口径:交易日∧数据区间内∧无行 → 停牌;共 %d 个缺行日" % len(missing))
    else:
        ck.add("停牌推导:2014 年 000001 缺行日", "存在", "无缺行", True, "该年无停牌,跳过")
    nc = store.read_table("namechange", symbols=["000005.SZ"]).sort_values("start_date")
    st_rows = nc[nc["name"].str.contains(r"^S?\*?ST", regex=True, na=False)]
    last_start = st_rows["start_date"].iloc[-1]
    before = (last_start - pd.Timedelta(days=1)).to_pydatetime()
    flags = ds.is_st_stock("000005.XSHE", [before, last_start.to_pydatetime()])
    # before 可能仍处于更早的 ST 区间,只硬核对 start 当日
    ck.add("ST 区间:000005 自 %s 起 ST" % last_start.date(), "[?, True]", repr(flags), flags[1] is True,
           "namechange 名称匹配 ^S?\\*?ST")
    log.info("停牌/ST 查询通过")


def run_backtest(cfg, ck, log, date):
    out = run_dir(TOPIC, "rq_check", date=date)
    state = {"bought": False}

    def init_(context):
        context.s = OBID

    def handle_bar(context, bar_dict):
        if not state["bought"]:
            order_shares(context.s, 10000)
            state["bought"] = True

    config = {
        "base": {"start_date": BT_START, "end_date": BT_END, "accounts": {"stock": 1_000_000},
                 "data_bundle_path": os.path.join(ROOT, "no_bundle")},
        "extra": {"log_level": "error"},
        "mod": {
            "store": {"enabled": True, "lib": "backtest.rqalpha_adapter.mod", "preload": [SYM]},
            "sys_progress": {"enabled": False},
            "sys_analyser": {"enabled": True, "plot": False, "benchmark": BENCH_OBID, "report_save_path": out},
        },
    }
    t0 = time.time()
    res = run_func(init=init_, handle_bar=handle_bar, config=config)["sys_analyser"]
    log.info("端到端回测 %.1fs,产出 %s", time.time() - t0, out)
    trades = res["trades"]
    first = trades.iloc[0]
    close_first = float(store.read_table("stock_daily", symbols=[SYM], start=BT_START, end=BT_START)["close"].iloc[0])
    ck.approx("成交价 = store %s 原始收盘(铁证,无 bundle)" % BT_START, close_first, float(first["last_price"]))
    pos = res["stock_positions"]
    q = pos["quantity"]
    q_before = int(q[pos.index < EX_DATE].iloc[-1])
    q_after = int(q[pos.index >= EX_DATE].iloc[0])
    adj = store.read_table("adj_factor", symbols=[SYM], start="2014-06-01", end="2014-06-30").sort_values("date")
    ratio = float(adj[adj["date"] == EX_DATE]["adj_factor"].iloc[0]) / float(adj[adj["date"] < EX_DATE]["adj_factor"].iloc[-1])
    ck.add("除权日股数按因子比例调整", "%d×%.5f=%d" % (q_before, ratio, round(q_before * ratio)), q_after,
           q_after == round(q_before * ratio))
    mv = pos["market_value"]
    mv_before, mv_after = float(mv[pos.index < EX_DATE].iloc[-1]), float(mv[pos.index >= EX_DATE].iloc[0])
    daily = store.read_table("stock_daily", symbols=[SYM], start="2014-06-11", end="2014-06-12").sort_values("date")
    c_prev, c_ex, pre_ex = float(daily["close"].iloc[0]), float(daily["close"].iloc[1]), float(daily["pre_close"].iloc[1])
    expected_ratio = ratio * c_ex / c_prev            # = c_ex / (c_prev/ratio) ≈ c_ex / pre_close
    ck.approx("除权日市值连续:mv(06-12)/mv(06-11) = 比值×收盘比", expected_ratio, mv_after / mv_before, rel=1e-3,
              note="≈ %.2f/%.2f(除权日收盘/除权昨收)= %.5f" % (c_ex, pre_ex, c_ex / pre_ex))
    bench = res["benchmark_portfolio"]["unit_net_value"]
    idx = store.read_table("index_daily", symbols=[BENCH_SYM], start="2014-06-01", end=BT_END).sort_values("date")
    prev = idx[idx["date"] < BT_START]["close"].iloc[-1]
    ck.approx("基准净值 = index_daily 累计收益(自回测前一日收盘起)", float(idx["close"].iloc[-1] / prev), float(bench.iloc[-1]), rel=1e-9)
    summary = res["summary"]
    return {"total_returns": summary.get("total_returns"), "benchmark_total_returns": summary.get("benchmark_total_returns"),
            "sharpe": summary.get("sharpe"), "out": out}


def check_preload(cfg, ck, log):
    uni = IndexUniverse(BENCH_SYM)
    syms = uni.all_symbols()
    ds = StoreDataSource(cfg)
    t0 = time.time()
    ds.preload(syms)
    took = time.time() - t0
    n_bars = sum(len(ds._cs_bars.get_bars(o)) for o in ds._cs_bars._cache)
    ck.add("沪深300 历史全成分预载(%d 只)" % len(syms), "<60 秒", "%.1f 秒,%d 根 bar" % (took, n_bars), took < 60,
           "一次下推读取 stock_daily + adj_factor,替代逐只全表扫描")
    log.info("预载 %d 只 %.1fs(%d bars)", len(syms), took, n_bars)


def write_report(ck, bt, date):
    path = os.path.join(report_dir(TOPIC, date=date), "phase_b_store_datasource_check.md")
    lines = [
        "# 卡3 阶段B · RQAlpha 接 store 数据源核对报告(%s)" % date,
        "",
        "结论:**%s**。RQAlpha 6.3.0 在不读任何 ricequant bundle 文件的情况下,全部数据来自我们的 store:" % ("全部通过" if ck.all_ok else "有不通过项"),
        "日历(core.calendar 文件模式←trade_cal)、instruments(stock_basic 含退市)+ 指数(index_daily)、",
        "日线 bar(stock_daily 原始价 + 品种规则表算涨跌停)、复权(adj_factor → ex_cum_factor 看历史 / 合成 split 过除权日)、",
        "停牌(缺行推导)、ST(namechange)。",
        "",
        "## 核对表",
        "",
        ck.to_md(),
        "",
        "## 端到端回测(买入持有 000001.XSHE,%s→%s,基准 000300.XSHG)" % (BT_START, BT_END),
        "",
        "- 总收益 %s | 基准总收益 %s | sharpe %s" % (bt["total_returns"], bt["benchmark_total_returns"], bt["sharpe"]),
        "- RQAlpha 报表目录:`%s`" % os.path.relpath(bt["out"], ROOT),
        "",
        "## 复权口径(书面声明,防重复复权)",
        "",
        "- bar 存**原始价**;`history_bars` 前复权 = 原始价 × f_t / f_dt(dt 为查询日),后复权 = 原始价 × f_t(= 自研 hfq)。",
        "- 持仓过除权日:adj_factor 变动日的比值 f_t/f_{t-1} 当作 RQAlpha 的拆股事件(股数×比值、成本/比值),市值连续;",
        "  现金分红**不单独供给**(已在因子里),故总回报口径与自研 hfq 引擎一致。分红税/分红再投资等 RQAlpha 选项无效。",
        "- 基类 BaseDataSource 会按上市日过滤因子并强插 1.0——我们的因子基准不是 1,已覆盖 `get_ex_cum_factor` 保留首值。",
        "",
        "## 停牌口径(书面声明)",
        "",
        "- Tushare daily 停牌日无行(全表 volume=0 的行为 0),故停牌 := 交易日 ∧ 在 [该股首个 bar, 数据末日] 内 ∧ 无行。",
        "  数据缺口会被当作停牌(保守:当日不可交易);上市前 / 数据末日后不算停牌。",
        "",
        "## 局限(阶段C 处理)",
        "",
        "- 上市首日(及科创/创业板前五日、主板首日 44%)的特殊涨跌停按\"首日 limit=NaN(无限制)\"近似;",
        "- ETF/基金(fund_daily)、期货未接入 instruments;退市清算走 RQAlpha `cash_return_by_stock_delisted`(默认 True,阶段C 红线核对);",
        "- 无风险利率为 config 常数(backtest.risk_free_rate),无收益率曲线表。",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="报告归档日期(续写历史主题时传原日期)")
    args = ap.parse_args()
    log = init("rqalpha_check")
    cfg = load_config()
    ck = Checks()
    ds = check_assembly(cfg, ck, log)
    check_adjust(ds, ck, log)
    check_flags(ds, ck, log)
    bt = run_backtest(cfg, ck, log, args.date)
    check_preload(cfg, ck, log)
    path = write_report(ck, bt, args.date)
    print(ck.to_md())
    print("报告:", path)
    return 0 if ck.all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
