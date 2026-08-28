# coding: utf-8
"""出信号入口(本平台终点,SOP S5):策略包 → orders_{signal_date}.csv + signal_log.md。

流程:加载策略包 → 交易日历(拒绝周内近似)→ data_asof = store 末日,asof = 请求日或今日前最近交易日 →
**新鲜度红线**:data_lag_days = (data_asof, asof] 内交易日数 > freshness_max_lag_days(策略包覆盖 > 平台 data 小节)
→ 拒绝出信号(不落文件)→ signal_date = min(asof, data_asof) → StoreContext 出权重 → apply_risk → 校验 → 落盘。
用法:python -m signals.run_signal --strategy toy_lowvol [--date YYYY-MM-DD]
"""
from core.bootstrap import init  # noqa: F401  必须第一行

import argparse
import datetime as dt
import os

import pandas as pd

from core.calendar import TradingCalendar
from core.config import ROOT, get, load_config
from core.outputs import report_dir
from data import store
from signals.schema import COLUMNS, validate_orders
from strategies.context import StoreContext
from strategies.package import build_strategy, load_package
from strategies.risk import apply_risk

PANEL_BUFFER_CAL_DAYS = 120     # 出信号面板起点提前的自然日数(覆盖 lookback + 假期余量;机制常量,非协议阈值)


class FreshnessError(RuntimeError):
    pass


def data_lag_days(cal, data_asof, asof):
    """数据末日之后、asof(含)之前的交易日数;asof ≤ data_asof → 0。"""
    data_asof, asof = pd.Timestamp(data_asof), pd.Timestamp(asof)
    if asof <= data_asof:
        return 0
    return int(len(cal.trading_days(data_asof + pd.Timedelta(days=1), asof)))


def last_holdings(strategy_id, cfg, root=None):
    """上一份信号文件的目标权重 = 假定已执行的当前持仓(出信号侧的持仓状态来源;没有则空)。"""
    from core.outputs import reports_root
    import glob
    files = sorted(glob.glob(os.path.join(reports_root(cfg, root), "*_信号_%s" % strategy_id, "orders_*.csv")))
    if not files:
        return {}
    df = pd.read_csv(files[-1], encoding="utf-8-sig")
    return {str(r["symbol"]): float(r["target_weight"]) for _, r in df.iterrows()}


def latest_trading_day(cal, today):
    days = cal.trading_days("1900-01-01", pd.Timestamp(today))
    if len(days) == 0:
        raise RuntimeError("交易日历里没有 %s 之前的交易日" % today)
    return days[-1]


def generate(strategy_id, cfg, root=None, asof=None, packages_root=None, today=None):
    root = root or ROOT
    today = pd.Timestamp(today or dt.date.today())
    pkg = load_package(strategy_id, root=packages_root)
    strategy = build_strategy(pkg)
    cal = TradingCalendar.load(cfg, root=root)
    if cal.source != "file":
        raise RuntimeError("交易日历不是文件模式(%s):禁止出信号" % cal.source)
    _, data_asof = store.date_range("stock_daily", root=root, cfg=cfg)
    if data_asof is None:
        raise RuntimeError("stock_daily 为空,无法出信号")
    asof_ts = pd.Timestamp(asof) if asof is not None else latest_trading_day(cal, today)
    max_lag = int(pkg.config.get("freshness_max_lag_days") or get(cfg, "data.freshness_max_lag_days"))
    lag = data_lag_days(cal, data_asof, asof_ts)
    if lag > max_lag:
        raise FreshnessError("数据不新鲜:store 末日 %s,asof %s,落后 %d 个交易日 > 红线 %d(策略 %s);禁止出信号"
                             % (data_asof.date(), asof_ts.date(), lag, max_lag, strategy_id))
    signal_date = min(asof_ts, data_asof)

    lookback = int(strategy.params.get("lookback", 0))
    start = (signal_date - pd.Timedelta(days=PANEL_BUFFER_CAL_DAYS + lookback * 2)).strftime("%Y-%m-%d")
    holdings = last_holdings(strategy_id, cfg, root)              # 有状态策略(如深跌反弹)需要"当前持仓":取上一份信号文件
    if any(k in strategy.params for k in ("drawdown_buy", "recover_sell")) or pkg.config.get("stateful"):
        start = "1900-01-01"                                       # 历史高点类策略需要全历史面板
    ctx = StoreContext.load(cfg, root, pkg.config["universe"], start, signal_date, holdings=holdings)
    raw_weights = strategy.signal(signal_date, ctx)
    weights = apply_risk(raw_weights, strategy.risk)

    prices = store.read_table("stock_daily", start=signal_date, end=signal_date, symbols=list(weights),
                              columns=["symbol", "close"], root=root, cfg=cfg).set_index("symbol")["close"]
    generated_at = dt.datetime.now().replace(microsecond=0).isoformat()
    rows = [{"strategy_id": strategy_id, "signal_date": signal_date.date().isoformat(), "symbol": sym, "side": "long",
             "target_weight": float(w), "ref_price": float(prices.get(sym, float("nan"))),
             "data_asof": data_asof.date().isoformat(), "data_lag_days": lag, "generated_at": generated_at}
            for sym, w in weights.items()]
    orders = pd.DataFrame(rows, columns=COLUMNS)
    validate_orders(orders)

    out_dir = report_dir("信号_" + strategy_id, date=today.date().isoformat(), cfg=cfg, root=root)
    path = os.path.join(out_dir, "orders_%s.csv" % signal_date.date().isoformat())
    orders.to_csv(path, index=False, encoding="utf-8-sig")
    meta = {"strategy_id": strategy_id, "name": pkg.config["name"], "status": pkg.config["status"],
            "signal_date": signal_date.date().isoformat(), "asof": asof_ts.date().isoformat(),
            "data_asof": data_asof.date().isoformat(), "data_lag_days": lag, "max_lag": max_lag,
            "n_raw": len(raw_weights), "n_orders": len(orders), "weight_sum": float(orders["target_weight"].sum()),
            "params": strategy.params, "risk": strategy.risk, "benchmark": strategy.benchmark,
            "crash_definition": pkg.config["crash_definition"], "generated_at": generated_at}
    _write_log(os.path.join(out_dir, "signal_log.md"), meta, orders)
    return {"path": path, "orders": orders, "meta": meta}


def _write_log(path, m, orders):
    lines = [
        "# 信号日志 · %s(%s)" % (m["strategy_id"], m["name"]), "",
        "- 状态:**%s**%s" % (m["status"], "(未放行,仅供研究,不得用于交易)" if m["status"] != "approved" else ""),
        "- 信号日 %s(asof %s;数据末日 %s,落后 %d 个交易日,红线 %d)" % (m["signal_date"], m["asof"], m["data_asof"], m["data_lag_days"], m["max_lag"]),
        "- 参数:%s;风控:%s;基准:%s" % (m["params"], m["risk"], m["benchmark"]),
        "- 原始选券 %d 只 → 风控后 %d 只,权重合计 %.4f;生成于 %s" % (m["n_raw"], m["n_orders"], m["weight_sum"], m["generated_at"]),
        "- 崩溃定义:" + " / ".join(m["crash_definition"]), "",
        "| symbol | target_weight | ref_price |", "|---|---|---|",
    ] + ["| %s | %.6f | %.2f |" % (r["symbol"], r["target_weight"], r["ref_price"]) for _, r in orders.iterrows()] + [""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--date", default=None, help="asof 日期(默认今日前最近交易日)")
    args = ap.parse_args()
    log = init("run_signal")
    cfg = load_config()
    out = generate(args.strategy, cfg, asof=args.date)
    m = out["meta"]
    log.info("信号文件 %s:%d 只,权重合计 %.4f,数据落后 %d 日(红线 %d),状态 %s",
             out["path"], m["n_orders"], m["weight_sum"], m["data_lag_days"], m["max_lag"], m["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
