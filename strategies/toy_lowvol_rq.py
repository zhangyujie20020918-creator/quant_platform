# coding: utf-8
"""向后兼容别名:RQAlpha 胶水已提为通用 strategies/rq_runner.py(任意策略包)。旧引用 make_strategy / plan_rebalance 仍可用。"""
from strategies.rq_runner import make_strategy, plan_rebalance  # noqa: F401
