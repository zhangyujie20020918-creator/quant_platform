# coding: utf-8
"""quant_platform 研发面板(卡6):只读 reports/,四屏——回测浏览器 / 因子 tear sheet / 信号 / 报告。

启动:streamlit run dashboard/app.py
reports 根目录来自 config meta.reports_dir;环境变量 QUANT_PLATFORM_REPORTS 可覆盖(测试钩子)。
本文件不计算、不落盘、不改任何文件;解析逻辑在 dashboard/catalog.py、dashboard/loaders.py(可测试)。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:                      # streamlit run 时 cwd 未必是仓库根
    sys.path.insert(0, ROOT)

import pandas as pd                           # noqa: E402
import streamlit as st                        # noqa: E402

from backtest.metrics import nav_stats                                        # noqa: E402
from core.config import load_config                                           # noqa: E402
from core.outputs import reports_root                                         # noqa: E402
from dashboard.catalog import scan_reports                                    # noqa: E402
from dashboard.loaders import (drawdown, load_navs, load_rq_portfolio, load_rq_positions,   # noqa: E402
                               load_rq_trades, load_summary, parse_md_table)

SCREENS = ["回测浏览器", "因子 tear sheet", "信号", "报告"]


def _reports_root():
    env = os.environ.get("QUANT_PLATFORM_REPORTS")
    if env:
        return env
    try:
        cfg = load_config()
    except FileNotFoundError:
        cfg = {}
    return reports_root(cfg)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _stats_table(navs):
    rows = {c: nav_stats(navs[c]) for c in navs.columns}
    df = pd.DataFrame(rows).T
    return df.rename(columns={"total_return": "总收益", "cagr": "年化", "max_drawdown": "最大回撤", "sharpe": "夏普"})


def _pick(label, items):
    if not items:
        st.info("reports/ 下未发现%s。" % label)
        return None
    return items[st.selectbox(label, range(len(items)), format_func=lambda i: items[i].label)]


def screen_backtests(cat):
    st.header("回测浏览器")
    st.subheader("净值对比(*_navs.csv)")
    nav_file = _pick("净值文件", cat.navs)
    if nav_file is not None:
        navs = load_navs(nav_file.path)
        st.line_chart(navs / navs.iloc[0])
        st.caption("归一化净值;下图为回撤")
        st.line_chart(pd.DataFrame({c: drawdown(navs[c]) for c in navs.columns}))
        st.dataframe(_stats_table(navs).style.format("{:.4f}"))
    st.subheader("RQAlpha 报表(*_runs/)")
    run = _pick("回测 run", cat.backtests)
    if run is None:
        return
    summary = load_summary(run.path)
    if summary:
        st.dataframe(pd.DataFrame({"指标": list(summary), "值": [str(v) for v in summary.values()]}), hide_index=True)
    if run.files.get("portfolio"):
        p = load_rq_portfolio(run.path)
        cols = [c for c in ("unit_net_value", "benchmark_unit_net_value") if c in p.columns]
        if cols:
            st.line_chart(p[cols])
    if run.files.get("positions"):
        pos = load_rq_positions(run.path)
        if len(pos):
            last = pos[pos["date"] == pos["date"].max()]
            st.markdown("**期末持仓(%s)**" % pos["date"].max().date())
            st.dataframe(last, hide_index=True)
    if run.files.get("trades"):
        t = load_rq_trades(run.path)
        st.markdown("**成交明细(共 %d 笔,显示最近 200)**" % len(t))
        st.dataframe(t.tail(200), hide_index=True)


def screen_factors(cat):
    st.header("因子 tear sheet")
    batch = _pick("因子检验批次", cat.factor_batches)
    if batch is None:
        return
    md = _read(batch.verdict_md)
    table = parse_md_table(md, "裁决总表")
    if table is not None:
        st.dataframe(table, hide_index=True)
    with st.expander("完整报告(factor_verdict.md)"):
        st.markdown(md)
    if not batch.tear_sheets:
        st.info("该批次没有 tear sheet 目录。")
        return
    fid = st.selectbox("因子", sorted(batch.tear_sheets))
    d = batch.tear_sheets[fid]
    files = sorted(os.listdir(d))
    for f in files:
        if f.endswith(".csv"):
            st.markdown("**%s**" % f)
            st.dataframe(pd.read_csv(os.path.join(d, f), encoding="utf-8-sig"))
    for f in files:
        if f.endswith(".png"):
            st.image(os.path.join(d, f), caption=f, use_container_width=True)


def screen_signals(cat):
    st.header("信号")
    sig = _pick("信号集", cat.signals)
    if sig is None:
        return
    for path in sig.orders:
        st.markdown("**%s**" % os.path.basename(path))
        st.dataframe(pd.read_csv(path, encoding="utf-8-sig"), hide_index=True)
    if sig.log:
        with st.expander("signal_log.md", expanded=True):
            st.markdown(_read(sig.log))


def screen_reports(cat):
    st.header("报告")
    if not cat.markdowns:
        st.info("reports/ 下没有 md 报告。")
        return
    labels = [os.path.relpath(m, cat.root) for m in cat.markdowns]
    idx = st.selectbox("报告", range(len(labels)), format_func=lambda i: labels[i])
    st.markdown(_read(cat.markdowns[idx]))


def main():
    st.set_page_config(page_title="quant_platform 研发面板", layout="wide")
    root = _reports_root()
    cat = scan_reports(root)
    st.sidebar.title("quant_platform 研发面板")
    st.sidebar.caption("只读 reports/:%s" % root)
    st.sidebar.caption("回测 %d · 净值文件 %d · 因子批次 %d · 信号集 %d · 报告 %d"
                       % (len(cat.backtests), len(cat.navs), len(cat.factor_batches), len(cat.signals), len(cat.markdowns)))
    screen = st.sidebar.radio("屏", SCREENS)
    {"回测浏览器": screen_backtests, "因子 tear sheet": screen_factors, "信号": screen_signals, "报告": screen_reports}[screen](cat)


main()
