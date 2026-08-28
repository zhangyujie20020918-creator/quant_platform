# coding: utf-8
"""因子实现库:一个因子一个模块 factors/lib/<id>.py,统一签名 compute(ctx) -> DataFrame(date × symbol)。

ctx = {"close": 后复权收盘面板, "open": 后复权开盘面板, "cfg": config};全历史向量化一次算完,
rolling 一律 min_periods = ceil(窗口 × protocol.min_periods_ratio),不足记 NaN。
因子元数据(五要素/状态)在 factors/registry.yaml,本目录只放公式实现。
"""
import importlib
import math

from core.config import get


def min_periods(window, cfg):
    return int(math.ceil(window * float(get(cfg, "protocol.min_periods_ratio"))))


def load_factor(factor_id):
    """→ 模块(含 compute);未实现 → KeyError。"""
    try:
        return importlib.import_module("factors.lib." + factor_id)
    except ModuleNotFoundError as e:
        if e.name and e.name.endswith(factor_id):
            raise KeyError("未实现的因子: %s(应在 factors/lib/%s.py)" % (factor_id, factor_id)) from None
        raise
