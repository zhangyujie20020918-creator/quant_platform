# coding: utf-8
"""RQAlpha 胶水(strategies/rq_runner)的执行模式:next_close = 信号日收盘算、次日收盘成交,滑点生效;
策略包级 execution/costs 生效;ctx.holdings() 在回测里来自 RQAlpha 持仓。合成 store。"""
import datetime as dt
import os
import textwrap

import pandas as pd
import pytest
import yaml
from rqalpha import run_func

from strategies.package import load_package
from strategies.rq_runner import make_strategy
from tests.rq_seed import seed

D = dt.date


def _pkg(tmp_path, mode, slippage):
    d = tmp_path / "pkgs" / "toy_exec"
    d.mkdir(parents=True, exist_ok=True)
    cfg = {"id": "toy_exec", "name": "执行模式测试", "type": "cross_sectional", "universe": {"index": "000300.SH"},
           "params": {"n_select": 1, "lookback": 3, "rebalance": "weekly_first", "filter_st": True},
           "benchmark": ["000300.SH"], "risk": {"max_weight": 1.0, "max_positions": 1},
           "execution": {"mode": mode, "slippage": slippage},
           "costs": {"commission_rate": 0.0002, "min_commission": 0.0, "stamp_tax_sell": [], "transfer_fee": []},
           "crash_definition": ["回撤 > 30%"], "status": "toy"}
    (d / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    (d / "strategy.py").write_text(textwrap.dedent('''
        from strategies.toy_lowvol.strategy import ToyLowVol
        def build(package):
            return ToyLowVol(package)
    '''), encoding="utf-8")
    return str(tmp_path / "pkgs")


def _run(root, cfg, pkg_root):
    cfg_path = os.path.join(root, "config.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)
    pkg = load_package("toy_exec", root=pkg_root)
    funcs = make_strategy(pkg, cfg=cfg, root=root)
    state = funcs.pop("state")
    config = {
        "base": {"start_date": "2014-06-04", "end_date": "2014-06-20", "accounts": {"stock": 1_000_000},
                 "data_bundle_path": os.path.join(root, "no_bundle_here")},
        "extra": {"log_level": "error"},
        "mod": {"store": {"enabled": True, "lib": "backtest.rqalpha_adapter.mod", "root": root, "config_path": cfg_path,
                          "costs": pkg.config["costs"]},
                "sys_simulation": {"slippage": pkg.config["execution"]["slippage"]},
                "sys_progress": {"enabled": False}, "sys_analyser": {"enabled": True, "plot": False}},
    }
    res = run_func(config=config, **funcs)["sys_analyser"]
    t = res["trades"]
    return [(pd.Timestamp(r["trading_datetime"]).date(), r["order_book_id"], r["side"], round(r["last_price"], 4), r["last_quantity"])
            for _, r in t.iterrows()], state


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("rq_exec"))
    return root, seed(root)


def test_next_close_executes_next_day_close_with_slippage(world, tmp_path):
    root, cfg = world
    trades, state = _run(root, cfg, _pkg(tmp_path, "next_close", 0.02))
    # 06-09 信号 → 06-10 收盘成交:000005 收盘 3.0 × (1+2%) = 3.06;数量按含滑点价整手:floor(1e6/(3.06×1.0002)/100)×100
    assert trades[0] == (D(2014, 6, 10), "000005.XSHE", "BUY", 3.06, 326700)
    # 06-16 信号(000005 已 ST → 换 600000)→ 06-17 收盘:卖 000005 3.0×0.98=2.94,买 600000 10×1.02=10.2
    assert trades[1][:4] == (D(2014, 6, 17), "000005.XSHE", "SELL", 2.94)
    assert trades[2][:4] == (D(2014, 6, 17), "600000.XSHG", "BUY", 10.2)
    mv, cash = 326700 * 3.0, 1_000_000 - 326700 * 3.06 - 326700 * 3.06 * 0.0002
    assert state["holdings_seen"][D(2014, 6, 16)] == {"000005.SZ": pytest.approx(mv / (mv + cash), abs=1e-4)}


def test_next_open_still_default_behaviour(world, tmp_path):
    root, cfg = world
    trades, _ = _run(root, cfg, _pkg(tmp_path, "next_open", 0.0))
    assert trades[0] == (D(2014, 6, 10), "000005.XSHE", "BUY", 3.0, 333200)
