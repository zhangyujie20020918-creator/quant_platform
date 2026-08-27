# coding: utf-8
"""A股股票品种规则表(蓝图原则3:交易规则挂在品种元数据上,引擎查表执行,代码零硬编码)。

数值全部来自 config `instruments.cn_stock`(example 给默认值):
- round_lot / market_tplus:整手与 T+1;
- costs:commission_rate / min_commission / stamp_tax_sell[{since, rate}] / transfer_fee[{since, rate}]——
  成本全查表,按生效日取值(dated_rate);
- price_limit.default / st:主板普通股与 ST 股幅度;
- boards.{KSH,GEM,BJS}:{since, price_limit, round_lot?}——板块自 since 起用统一幅度(该板块 ST 亦同幅度;
  since 之前按主板规则,对应创业板 2020-08-24 改革前 10%/ST 5%);round_lot 覆盖板块最小下单股数。
局限(书面声明):上市首日/前五日无涨跌停的特例不在此表,由 bar 层按"首个交易日 limit=NaN"近似。
"""
import numpy as np
import pandas as pd

from core.config import get

_MARKET_TO_BOARD = {"主板": "MainBoard", "中小板": "MainBoard", "创业板": "GEM", "科创板": "KSH", "北交所": "BJS"}


def board_type(market):
    """Tushare market 文本 → RQAlpha board_type;未知/缺失按主板。"""
    return _MARKET_TO_BOARD.get(market, "MainBoard")


def rules(cfg):
    return get(cfg, "instruments.cn_stock")


def price_limit_ratios(board, dates, is_st, cfg):
    """逐日涨跌停幅度(比例数组)。board: RQAlpha board_type;dates: DatetimeIndex;is_st: 同长布尔数组。"""
    pl = get(cfg, "instruments.cn_stock.price_limit")
    dates = pd.DatetimeIndex(dates)
    is_st = np.asarray(is_st, dtype=bool)
    out = np.where(is_st, float(pl["st"]), float(pl["default"]))
    board_rule = get(cfg, "instruments.cn_stock.boards", {}).get(board)
    if board_rule:
        since = pd.Timestamp(board_rule["since"])
        out = np.where(dates >= since, float(board_rule["price_limit"]), out)
    return out


def round_lot(board, cfg):
    """板块最小下单股数:boards.{板块}.round_lot 覆盖,否则 cn_stock.round_lot。"""
    board_rule = get(cfg, "instruments.cn_stock.boards", {}).get(board) or {}
    return int(board_rule.get("round_lot", get(cfg, "instruments.cn_stock.round_lot")))


def dated_rate(entries, date):
    """按生效日取费率:entries=[{since, rate}],取 since ≤ date 的最新一条;无则 0.0。"""
    date = pd.Timestamp(date)
    rate = 0.0
    for e in sorted(entries or [], key=lambda x: pd.Timestamp(x["since"])):
        if pd.Timestamp(e["since"]) <= date:
            rate = float(e["rate"])
    return rate


def cost_rules(cfg, overrides=None):
    """instruments.cn_stock.costs,可用 overrides(dict)覆盖个别键(如交叉验证时对齐口径)。"""
    rules_ = dict(get(cfg, "instruments.cn_stock.costs"))
    rules_.update(overrides or {})
    return rules_
