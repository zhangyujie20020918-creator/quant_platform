# coding: utf-8
"""面板目录扫描 / 加载 / 解析(纯 python,只读):合成 reports 树上验证识别与解析,并断言不写任何文件。"""
import base64
import os

import pandas as pd
import pytest

from dashboard.catalog import scan_reports
from dashboard.loaders import (drawdown, load_navs, load_rq_portfolio, load_rq_positions, load_rq_trades,
                               load_summary, parse_md_table)

# 1×1 透明 PNG
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
VERDICT_MD = """# 卡4 因子检验报告(2026-08-28)

## 一、批前声明

- 阈值 ...

## 二、裁决总表

| 因子 | 角色 | IC_is | 裁决 |
|---|---|---|---|
| vol_20 | candidate | -0.0435 | **tested_weak** |
| random_control | negative_control | 0.0029 | **rejected** |

## 三、对照组

- rev_20:阳性对照首次运行
"""


def _touch(path, text="", binary=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if binary is not None:
        with open(path, "wb") as f:
            f.write(binary)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("reports"))
    c = os.path.join(root, "2026-08-28_卡3阶段C")
    _touch(os.path.join(c, "toy_lowvol_cross_validation.md"), "# 交叉验证\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    _touch(os.path.join(c, "toy_lowvol_navs.csv"),
           "date,self_built,rqalpha_align\n2014-06-04,1000000,1000000\n2014-06-05,1010000,1005000\n2014-06-06,990000,995000\n")
    run = os.path.join(c, "rq_full_runs")
    _touch(os.path.join(run, "portfolio.csv"),
           "date,cash,total_value,market_value,unit_net_value\n2014-06-04,1000000,1000000,0,1.0\n2014-06-05,500,1010000,1009500,1.01\n")
    _touch(os.path.join(run, "trades.csv"),
           "datetime,trading_datetime,order_book_id,symbol,side,last_quantity,last_price,commission,tax,transaction_cost\n"
           "2014-06-04 15:00:00,2014-06-04 15:00:00,000001.XSHE,平安银行,BUY,10000,11.3,22.6,0,22.6\n")
    _touch(os.path.join(run, "stock_positions.csv"),
           "date,order_book_id,symbol,quantity,last_price,market_value\n2014-06-04,000001.XSHE,平安银行,10000,11.3,113000\n")
    pd.DataFrame([["annualized_returns", 0.0429], ["max_drawdown", 0.3099]]).to_excel(os.path.join(run, "summary.xlsx"), header=False, index=False)

    f = os.path.join(root, "2026-08-28_卡4因子检验")
    _touch(os.path.join(f, "factor_verdict.md"), VERDICT_MD)
    t = os.path.join(f, "tear_vol_20_runs")
    _touch(os.path.join(t, "vol_20_tear_01.png"), binary=PNG)
    _touch(os.path.join(t, "vol_20_tear_02.png"), binary=PNG)
    _touch(os.path.join(t, "vol_20_ic.csv"), ",1D,5D\nmean,-0.02,-0.03\n")
    _touch(os.path.join(t, "vol_20_quantile_returns.csv"), "factor_quantile,1D,5D\n1,0.001,0.002\n")

    s = os.path.join(root, "2026-08-28_信号_toy_lowvol")
    _touch(os.path.join(s, "orders_2026-08-26.csv"),
           "strategy_id,signal_date,symbol,side,target_weight,ref_price,data_asof,data_lag_days,generated_at\n"
           "toy_lowvol,2026-08-26,000166.SZ,long,0.05,4.56,2026-08-26,0,2026-08-28T12:13:28\n")
    _touch(os.path.join(s, "signal_log.md"), "# 信号日志\n")
    _touch(os.path.join(root, "not_a_report.txt"), "x")                        # 非报告目录/文件应被忽略
    return root


def _snapshot(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            out[p] = os.path.getsize(p)
    return out


def test_scan_finds_backtests_navs_factors_signals_and_markdowns(tree):
    cat = scan_reports(tree)
    assert [d.topic for d in cat.dirs] == ["信号_toy_lowvol", "卡4因子检验", "卡3阶段C"] or len(cat.dirs) == 3
    bt = cat.backtests
    assert len(bt) == 1 and bt[0].name == "rq_full" and bt[0].topic == "卡3阶段C" and bt[0].files["summary"].endswith("summary.xlsx")
    assert len(cat.navs) == 1 and cat.navs[0].columns == ["self_built", "rqalpha_align"]
    fb = cat.factor_batches
    assert len(fb) == 1 and fb[0].verdict_md.endswith("factor_verdict.md") and list(fb[0].tear_sheets) == ["vol_20"]
    sg = cat.signals
    assert len(sg) == 1 and sg[0].strategy == "toy_lowvol" and len(sg[0].orders) == 1 and sg[0].log.endswith("signal_log.md")
    assert any(m.endswith("toy_lowvol_cross_validation.md") for m in cat.markdowns)


def test_scan_ignores_missing_root(tmp_path):
    cat = scan_reports(str(tmp_path / "nope"))
    assert cat.dirs == [] and cat.backtests == []


def test_loaders_parse_rqalpha_outputs(tree):
    run = scan_reports(tree).backtests[0]
    p = load_rq_portfolio(run.path)
    assert list(p.index) == list(pd.to_datetime(["2014-06-04", "2014-06-05"])) and p["total_value"].iloc[-1] == 1010000
    t = load_rq_trades(run.path)
    assert t.iloc[0]["order_book_id"] == "000001.XSHE" and t.iloc[0]["last_price"] == 11.3
    pos = load_rq_positions(run.path)
    assert pos.iloc[0]["quantity"] == 10000
    s = load_summary(run.path)
    assert s["annualized_returns"] == pytest.approx(0.0429) and s["max_drawdown"] == pytest.approx(0.3099)


def test_load_navs_and_drawdown(tree):
    nav = load_navs(scan_reports(tree).navs[0].path)
    assert list(nav.columns) == ["self_built", "rqalpha_align"] and nav.index.name == "date"
    dd = drawdown(nav["self_built"])
    assert dd.iloc[0] == 0 and dd.iloc[-1] == pytest.approx(990000 / 1010000 - 1)


def test_parse_md_table_after_heading(tree):
    fb = scan_reports(tree).factor_batches[0]
    with open(fb.verdict_md, encoding="utf-8") as f:
        md = f.read()
    df = parse_md_table(md, "裁决总表")
    assert list(df.columns) == ["因子", "角色", "IC_is", "裁决"] and df.iloc[0]["因子"] == "vol_20" and len(df) == 2
    assert parse_md_table(md, "不存在的标题") is None


def test_scan_and_load_are_read_only(tree):
    before = _snapshot(tree)
    cat = scan_reports(tree)
    load_rq_portfolio(cat.backtests[0].path)
    load_summary(cat.backtests[0].path)
    load_navs(cat.navs[0].path)
    assert _snapshot(tree) == before
