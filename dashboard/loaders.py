# coding: utf-8
"""报表文件加载与解析(只读):RQAlpha 报表 CSV/xlsx、净值对比 CSV、md 表格。CSV 一律 utf-8-sig(RQAlpha 带 BOM)。"""
import os

import pandas as pd


def _csv(path, **kw):
    return pd.read_csv(path, encoding="utf-8-sig", **kw)


def load_rq_portfolio(run_dir):
    df = _csv(os.path.join(run_dir, "portfolio.csv"), parse_dates=["date"])
    return df.set_index("date").sort_index()


def load_rq_trades(run_dir):
    df = _csv(os.path.join(run_dir, "trades.csv"))
    df = df.loc[:, ~df.columns.duplicated()]                    # RQAlpha 的 datetime 既是索引又是列
    if "trading_datetime" in df.columns:
        df["trading_datetime"] = pd.to_datetime(df["trading_datetime"])
    return df


def load_rq_positions(run_dir):
    df = _csv(os.path.join(run_dir, "stock_positions.csv"), parse_dates=["date"])
    return df


def load_summary(run_dir):
    """summary.xlsx(两列:指标名 / 值)→ dict;缺文件 → {}。"""
    path = os.path.join(run_dir, "summary.xlsx")
    if not os.path.exists(path):
        return {}
    x = pd.read_excel(path, header=None)
    return {str(k): v for k, v in zip(x.iloc[:, 0], x.iloc[:, 1])}


def load_navs(path):
    df = _csv(path, parse_dates=["date"]).set_index("date").sort_index()
    df.index.name = "date"
    return df


def drawdown(nav):
    nav = nav.dropna()
    return nav / nav.cummax() - 1


def parse_md_table(md, anchor):
    """标题含 anchor 的小节之后的第一张 markdown 表 → DataFrame(全部字符串列);找不到 → None。"""
    lines = md.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("#") and anchor in l), None)
    if start is None:
        return None
    i = start + 1
    while i < len(lines) and not lines[i].lstrip().startswith("|"):
        if lines[i].startswith("#"):
            return None
        i += 1
    rows = []
    while i < len(lines) and lines[i].lstrip().startswith("|"):
        rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
        i += 1
    if len(rows) < 2:
        return None
    header, body = rows[0], [r for r in rows[1:] if not all(set(c) <= set("-: ") for c in r)]
    return pd.DataFrame([r[:len(header)] + [""] * (len(header) - len(r)) for r in body], columns=header)
