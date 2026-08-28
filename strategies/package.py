# coding: utf-8
"""策略包(蓝图原则5):strategies/<id>/{config.yaml, strategy.py, 说明书.md}。

config.yaml 必填:id / name / type(cross_sectional|time_series)/ universe / params / benchmark(≥1,原则6)/
risk / crash_definition(SOP S5 崩溃定义,≥1 条);可选 freshness_max_lag_days、status(toy|research|approved)、
approved_by(status=approved 时必填 = 人类签字)。strategy.py 须提供 build(package) -> Strategy。
"""
import importlib.util
import os

import yaml

from core.config import ROOT
from strategies.base import Strategy

REQUIRED = ("id", "name", "type", "universe", "params", "benchmark", "risk", "crash_definition")
TYPES = ("cross_sectional", "time_series")
STATUSES = ("toy", "research", "approved")


class PackageError(ValueError):
    pass


class Package:
    def __init__(self, strategy_id, directory, config):
        self.id, self.dir, self.config = strategy_id, directory, config

    def __repr__(self):
        return "Package(%s)" % self.id


def _validate(strategy_id, cfg):
    if not isinstance(cfg, dict):
        raise PackageError("策略包 %s 的 config.yaml 不是映射" % strategy_id)
    missing = [k for k in REQUIRED if k not in cfg or cfg[k] in (None, "", [], {})]
    if missing:
        raise PackageError("策略包 %s config 缺项: %s" % (strategy_id, ", ".join(missing)))
    if cfg["id"] != strategy_id:
        raise PackageError("策略包目录 %s 与 config.id %s 不一致" % (strategy_id, cfg["id"]))
    if cfg["type"] not in TYPES:
        raise PackageError("策略包 %s type 非法: %r(应为 %s)" % (strategy_id, cfg["type"], "/".join(TYPES)))
    if not isinstance(cfg["benchmark"], list) or not cfg["benchmark"]:
        raise PackageError("策略包 %s benchmark 必须是非空列表(原则6:基准可配置但必须声明)" % strategy_id)
    if not isinstance(cfg["crash_definition"], list) or not cfg["crash_definition"]:
        raise PackageError("策略包 %s crash_definition 必须是非空列表(SOP S5 崩溃定义制)" % strategy_id)
    status = cfg.get("status") or "toy"
    if status not in STATUSES:
        raise PackageError("策略包 %s status 非法: %r(应为 %s)" % (strategy_id, status, "/".join(STATUSES)))
    if status == "approved" and not cfg.get("approved_by"):
        raise PackageError("策略包 %s status=approved 但无 approved_by(人类签字)" % strategy_id)
    cfg["status"] = status
    return cfg


def load_package(strategy_id, root=None):
    root = root or os.path.join(ROOT, "strategies")
    directory = os.path.join(root, strategy_id)
    path = os.path.join(directory, "config.yaml")
    if not os.path.exists(path):
        raise PackageError("策略包不存在或缺 config.yaml: %s" % path)
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return Package(strategy_id, directory, _validate(strategy_id, cfg))


def build_strategy(package):
    path = os.path.join(package.dir, "strategy.py")
    if not os.path.exists(path):
        raise PackageError("策略包 %s 缺 strategy.py" % package.id)
    spec = importlib.util.spec_from_file_location("strategies._pkg_%s" % package.id, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    build = getattr(module, "build", None)
    if build is None:
        raise PackageError("策略包 %s 的 strategy.py 缺 build(package)" % package.id)
    strategy = build(package)
    if not isinstance(strategy, Strategy):
        raise PackageError("策略包 %s build() 未返回 Strategy 子类实例" % package.id)
    if strategy.type != package.config["type"]:
        raise PackageError("策略包 %s 原型类型不一致: config=%s, 类=%s" % (package.id, package.config["type"], strategy.type))
    return strategy
