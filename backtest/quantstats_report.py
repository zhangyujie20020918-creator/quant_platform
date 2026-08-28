# coding: utf-8
"""quantstats 薄封装:净值(或含 date 列的 navs CSV)→ html 绩效报告。

用法:python -m backtest.quantstats_report <navs.csv> --strategy rqalpha_full --benchmark benchmark --out x.html
"""
import argparse
import os

import matplotlib
matplotlib.use("Agg")
import pandas as pd                     # noqa: E402
import quantstats as qs                 # noqa: E402


def nav_report(nav, benchmark, out_html, title="strategy"):
    """nav / benchmark:净值 Series(DatetimeIndex)。返回写出的 html 路径。"""
    rets = nav.sort_index().pct_change().dropna()
    rets.index = pd.DatetimeIndex(rets.index)
    bench = None
    if benchmark is not None:
        bench = benchmark.sort_index().pct_change().dropna()
        bench.index = pd.DatetimeIndex(bench.index)
        bench = bench.reindex(rets.index).fillna(0.0)
    os.makedirs(os.path.dirname(os.path.abspath(out_html)), exist_ok=True)
    qs.reports.html(rets, benchmark=bench, output=out_html, title=title, download_filename=os.path.basename(out_html))
    return out_html


def main():
    from core.bootstrap import init
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--strategy", required=True, help="策略净值列名")
    ap.add_argument("--benchmark", default=None, help="基准净值列名(可省)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="strategy")
    args = ap.parse_args()
    init("quantstats_report")
    df = pd.read_csv(args.csv, parse_dates=["date"]).set_index("date")
    bench = df[args.benchmark] if args.benchmark else None
    print(nav_report(df[args.strategy], bench, args.out, title=args.title))


if __name__ == "__main__":
    main()
