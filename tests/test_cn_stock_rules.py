# coding: utf-8
"""A股股票品种规则表(蓝图原则3):板块映射与涨跌停幅度查表,数值全部来自 config。"""
import numpy as np
import pandas as pd

from instruments.cn_stock import board_type, price_limit_ratios, round_lot

RULES = {
    "round_lot": 100, "market_tplus": 1,
    "price_limit": {"default": 0.10, "st": 0.05},
    "boards": {"KSH": {"since": "2019-07-22", "price_limit": 0.20, "round_lot": 200},
               "GEM": {"since": "2020-08-24", "price_limit": 0.20},
               "BJS": {"since": "2020-07-27", "price_limit": 0.30}},
}
CFG = {"instruments": {"cn_stock": RULES}}


def test_board_type_maps_tushare_market_to_rqalpha_board():
    assert board_type("主板") == "MainBoard"
    assert board_type("创业板") == "GEM"
    assert board_type("科创板") == "KSH"
    assert board_type("北交所") == "BJS"
    assert board_type(None) == "MainBoard"          # 缺失按主板处理(数据里有一条 market 为空)


def test_main_board_default_and_st_ratio():
    dates = pd.to_datetime(["2015-01-05", "2015-01-06"])
    st = np.array([False, True])
    assert price_limit_ratios("MainBoard", dates, st, CFG).tolist() == [0.10, 0.05]


def test_gem_switches_to_20pct_on_reform_date_and_ignores_st():
    dates = pd.to_datetime(["2020-08-21", "2020-08-24"])
    st = np.array([True, True])
    assert price_limit_ratios("GEM", dates, st, CFG).tolist() == [0.05, 0.20]


def test_ksh_and_bjs_use_board_ratio():
    dates = pd.to_datetime(["2022-03-01"])
    assert price_limit_ratios("KSH", dates, np.array([False]), CFG).tolist() == [0.20]
    assert price_limit_ratios("BJS", dates, np.array([False]), CFG).tolist() == [0.30]


def test_round_lot_board_override():
    assert round_lot("MainBoard", CFG) == 100
    assert round_lot("KSH", CFG) == 200
    assert round_lot("GEM", CFG) == 100
