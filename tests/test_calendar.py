# coding: utf-8
import logging

import pandas as pd
import pytest

from core.calendar import TradingCalendar


def test_weekday_approx_basic():
    cal = TradingCalendar()
    assert cal.source == "weekday_approx"
    assert cal.is_trading_day("2026-08-24")        # 周一
    assert not cal.is_trading_day("2026-08-22")    # 周六
    assert cal.next_trading_day("2026-08-21") == pd.Timestamp("2026-08-24")   # 周五→周一
    assert cal.next_trading_day("2026-08-21", n=2) == pd.Timestamp("2026-08-25")
    assert cal.prev_trading_day("2026-08-24") == pd.Timestamp("2026-08-21")
    with pytest.raises(ValueError):
        cal.next_trading_day("2026-08-21", n=0)


def _file_cal(tmp_path):
    """2026-01~02 的工作日,人为挖掉 01-01/01-02(元旦)与 02-16/02-17 模拟节假日。"""
    days = pd.bdate_range("2026-01-01", "2026-02-27")
    holidays = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-02-16", "2026-02-17"])
    days = days[~days.isin(holidays)]
    p = tmp_path / "trading_days.csv"
    pd.DataFrame({"date": days.strftime("%Y-%m-%d")}).to_csv(p, index=False)
    return p, days


def test_file_mode_is_authoritative_over_weekday(tmp_path):
    p, days = _file_cal(tmp_path)
    cal = TradingCalendar.load({"calendar": {"file": str(p)}}, root=str(tmp_path))
    assert cal.source == "file"
    assert not cal.is_trading_day("2026-01-02")    # 周五但文件说是假日
    assert cal.is_trading_day("2026-01-05")
    assert cal.next_trading_day("2026-01-02") == pd.Timestamp("2026-01-05")   # 从非交易日起步
    assert cal.next_trading_day("2026-01-05") == pd.Timestamp("2026-01-06")
    assert cal.prev_trading_day("2026-01-06") == pd.Timestamp("2026-01-05")
    with pytest.raises(IndexError):
        cal.prev_trading_day("2026-01-05")          # 文件范围之外
    jan = cal.trading_days("2026-01-01", "2026-01-31")
    assert len(jan) == len(days[days < "2026-02-01"]) == 20


def test_load_falls_back_with_warning_when_file_missing(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="core.calendar"):
        cal = TradingCalendar.load({"calendar": {"file": "nope/trading_days.csv"}}, root=str(tmp_path))
    assert cal.source == "weekday_approx"
    assert "退化" in caplog.text


def test_rebalance_dates_frequencies(tmp_path):
    p, _ = _file_cal(tmp_path)
    cal = TradingCalendar.load({"calendar": {"file": str(p)}}, root=str(tmp_path))
    monthly = cal.rebalance_dates("2026-01-01", "2026-02-27", freq="monthly_first")
    assert list(monthly) == [pd.Timestamp("2026-01-05"), pd.Timestamp("2026-02-02")]
    weekly = cal.rebalance_dates("2026-02-09", "2026-02-20", freq="weekly_first")
    assert list(weekly) == [pd.Timestamp("2026-02-09"), pd.Timestamp("2026-02-18")]   # 16/17挖掉
    with pytest.raises(ValueError):
        cal.rebalance_dates("2026-01-01", "2026-01-31", freq="daily")
    approx = TradingCalendar().rebalance_dates("2026-01-01", "2026-02-28")
    assert list(approx) == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-02")]
    assert len(cal.rebalance_dates("2026-03-01", "2026-03-31")) == 0
