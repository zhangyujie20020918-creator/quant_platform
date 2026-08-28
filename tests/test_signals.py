# coding: utf-8
"""信号文件契约 + 新鲜度红线 + run_signal 端到端(合成 store);回测与出信号同一逻辑(与 test_toy_lowvol_rq 的选券对照)。"""
import datetime as dt
import os
import textwrap

import pandas as pd
import pytest
import yaml

from core.calendar import TradingCalendar
from data import store
from data.fetch import export_calendar
from signals.run_signal import FreshnessError, data_lag_days, generate
from signals.schema import COLUMNS, SignalError, validate_orders
from tests.rq_seed import seed

D = dt.date


def _orders(**over):
    row = {"strategy_id": "toy", "signal_date": "2014-06-20", "symbol": "600000.SH", "side": "long",
           "target_weight": 0.5, "ref_price": 10.0, "data_asof": "2014-06-20", "data_lag_days": 0,
           "generated_at": "2014-06-20T16:00:00"}
    row.update(over)
    return pd.DataFrame([row], columns=COLUMNS)


def test_validate_orders_accepts_good_file():
    validate_orders(_orders())


@pytest.mark.parametrize("bad", [
    lambda df: df.drop(columns=["ref_price"]),
    lambda df: df.assign(target_weight=1.5),
    lambda df: df.assign(target_weight=-0.1),
    lambda df: df.assign(side="short"),
    lambda df: df.assign(symbol="600000"),
    lambda df: pd.concat([df, df]),                                   # 重复标的
    lambda df: pd.concat([df, df.assign(symbol="000001.SZ", target_weight=0.6)]),   # 合计 > 1
])
def test_validate_orders_rejects(bad):
    with pytest.raises(SignalError):
        validate_orders(bad(_orders()))


def test_data_lag_days_counts_trading_days_after_data():
    cal = TradingCalendar(days=pd.bdate_range("2014-06-02", "2014-06-30"), source="file")
    assert data_lag_days(cal, D(2014, 6, 16), D(2014, 6, 18)) == 2
    assert data_lag_days(cal, D(2014, 6, 16), D(2014, 6, 16)) == 0
    assert data_lag_days(cal, D(2014, 6, 16), D(2014, 6, 10)) == 0        # 回看历史不算过期


# ---------- 端到端 ----------

def _toy_pkg(tmp_path, freshness=None):
    d = tmp_path / "pkgs" / "toy_small"
    d.mkdir(parents=True, exist_ok=True)
    cfg = {"id": "toy_small", "name": "玩具(小参数)", "type": "cross_sectional", "universe": {"index": "000300.SH"},
           "params": {"n_select": 1, "lookback": 3, "rebalance": "weekly_first", "filter_st": True},
           "benchmark": ["000300.SH"], "risk": {"max_weight": 1.0, "max_positions": 1},
           "crash_definition": ["回撤 > 30%"], "status": "toy"}
    if freshness is not None:
        cfg["freshness_max_lag_days"] = freshness
    (d / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    (d / "strategy.py").write_text(textwrap.dedent('''
        from strategies.toy_lowvol.strategy import ToyLowVol
        def build(package):
            return ToyLowVol(package)
    '''), encoding="utf-8")
    return str(tmp_path / "pkgs")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("sig"))
    cfg = seed(root)
    cfg["data"]["freshness_max_lag_days"] = 2
    return root, cfg


def test_generate_writes_valid_orders_file(world, tmp_path):
    root, cfg = world
    out = generate("toy_small", cfg, root=root, packages_root=_toy_pkg(tmp_path), today=D(2014, 6, 20))
    df = out["orders"]
    validate_orders(df)
    assert os.path.exists(out["path"]) and out["path"].endswith("orders_2014-06-20.csv")
    assert df["symbol"].tolist() == ["600000.SH"] and df["target_weight"].tolist() == [1.0]    # 000005 已 ST 被剔
    assert df["ref_price"].iloc[0] == 10.0 and df["data_asof"].iloc[0] == "2014-06-20" and df["data_lag_days"].iloc[0] == 0
    assert os.path.exists(os.path.join(os.path.dirname(out["path"]), "signal_log.md"))


def test_generate_historical_asof_matches_backtest_picks(world, tmp_path):
    # 与 test_toy_lowvol_rq(RQAlphaContext)同一世界同参数:06-09 选 000005,06-16 选 600000
    root, cfg = world
    pk = _toy_pkg(tmp_path)
    assert generate("toy_small", cfg, root=root, packages_root=pk, asof=D(2014, 6, 9), today=D(2014, 6, 20))["orders"]["symbol"].tolist() == ["000005.SZ"]
    assert generate("toy_small", cfg, root=root, packages_root=pk, asof=D(2014, 6, 16), today=D(2014, 6, 20))["orders"]["symbol"].tolist() == ["600000.SH"]


def _extend_calendar(root, cfg, days):
    cal = pd.DataFrame({"date": pd.to_datetime(days), "exchange": "SSE", "is_open": True, "source": "tushare"})
    store.write_part("trade_cal", "tushare", "extra", cal, root=root)
    store.consolidate("trade_cal", root=root)
    export_calendar(cfg, root=root)


def test_generate_refuses_stale_data(tmp_path_factory, tmp_path):
    root = str(tmp_path_factory.mktemp("stale"))
    cfg = seed(root)
    cfg["data"]["freshness_max_lag_days"] = 1
    _extend_calendar(root, cfg, ["2014-06-23", "2014-06-24"])           # 日历延伸 2 个交易日,数据仍到 06-20
    with pytest.raises(FreshnessError):
        generate("toy_small", cfg, root=root, packages_root=_toy_pkg(tmp_path), today=D(2014, 6, 24))
    assert not any(f.startswith("orders_") for _, _, fs in os.walk(os.path.join(root, "reports")) for f in fs)
    # 策略包放宽到 2 → 允许,并把落后天数写进文件
    out = generate("toy_small", cfg, root=root, packages_root=_toy_pkg(tmp_path, freshness=2), today=D(2014, 6, 24))
    assert out["orders"]["data_lag_days"].iloc[0] == 2 and out["path"].endswith("orders_2014-06-20.csv")


def test_generic_backtest_runner_on_package(world, tmp_path):
    # 傻瓜版回测入口:任意策略包 → RQAlpha → 报告(与 run_signal 同一策略包、同一 signal())
    from backtest.run_strategy import run_strategy
    root, cfg = world
    cfg_path = os.path.join(root, "config.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)
    out = run_strategy("toy_small", cfg, "2014-06-04", "2014-06-20", root=root, packages_root=_toy_pkg(tmp_path),
                       config_path=cfg_path, date="2014-06-20")
    assert os.path.exists(out["report"]) and out["report"].endswith("backtest.md")
    assert len(out["nav"]) == 13 and out["signals"] == 3 and out["trades"] >= 1
    assert os.path.exists(os.path.join(os.path.dirname(out["report"]), "nav.csv"))


def test_store_context_panels_and_holdings(world):
    from strategies.context import StoreContext
    root, cfg = world
    ctx = StoreContext.load(cfg, root, {"boards": ["主板", "创业板"]}, "2014-06-01", "2014-06-20",
                            holdings={"600000.SH": 0.5})
    close = ctx.panel("close", "2014-06-12")
    assert close.index.max() == pd.Timestamp("2014-06-12") and "600000.SH" in close.columns      # ≤asof,后复权
    assert close.loc["2014-06-12", "000001.SZ"] == pytest.approx(9.71 * 71.054)
    amt = ctx.panel("amount", "2014-06-12")
    assert amt.loc["2014-06-12", "000001.SZ"] == pytest.approx(9.71 * 1_000_000)                # 原始成交额
    assert ctx.holdings() == {"600000.SH": 0.5}
    assert "688001.SH" not in ctx.constituents("2014-06-12") and "000005.SZ" in ctx.constituents("2014-06-12")
