# coding: utf-8
"""config.yaml 加载与点路径访问(唯一参数源;自cb_quant平移+扩展)。

用法:
    from core.config import load_config, get
    cfg = load_config()
    cfg = load_config(overrides=["data.freshness_max_lag_days=3"])
    get(cfg, "protocol.ic_min")                 # 点路径读取,键不存在则报错
    get(cfg, "calendar.file", "cache/calendar/trading_days.csv")   # 带默认值

阈值治理约定:一切数值判据住 config(protocol小节),代码只写机制。
"""
import copy
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(ROOT, "config.yaml")
EXAMPLE_CONFIG_PATH = os.path.join(ROOT, "config.example.yaml")

_MISSING = object()


def _parse_value(raw):
    """override 的字符串值按 YAML 字面量解析(数字/布尔/null/字符串)。"""
    return yaml.safe_load(raw)


def _set_by_path(cfg, dotted_path, value):
    keys = dotted_path.split(".")
    node = cfg
    for k in keys[:-1]:
        if k not in node or not isinstance(node[k], dict):
            raise KeyError("config 覆盖路径不存在: %s(卡在 '%s')" % (dotted_path, k))
        node = node[k]
    last = keys[-1]
    if last not in node:
        raise KeyError("config 覆盖路径不存在: %s(末端键 '%s' 不存在)" % (dotted_path, last))
    node[last] = value


def apply_overrides(cfg, overrides):
    """overrides: ["a.b.c=1", "x.y=foo"] 形式的点路径覆盖列表,原地修改并返回 cfg。"""
    for item in overrides or []:
        if "=" not in item:
            raise ValueError("override 格式应为 path=value,收到: %r" % item)
        path, raw_value = item.split("=", 1)
        _set_by_path(cfg, path.strip(), _parse_value(raw_value.strip()))
    return cfg


def get(cfg, dotted_path, default=_MISSING):
    """点路径读取。键不存在时:给了default返回default,否则KeyError(拒绝静默吞错)。"""
    node = cfg
    for k in dotted_path.split("."):
        if not isinstance(node, dict) or k not in node:
            if default is _MISSING:
                raise KeyError("config 路径不存在: %s(卡在 '%s')" % (dotted_path, k))
            return default
        node = node[k]
    return node


def load_config(path=None, overrides=None):
    """读取 config.yaml,应用 overrides,返回 dict。每次调用返回独立副本。"""
    path = path or DEFAULT_CONFIG_PATH
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg = apply_overrides(cfg, overrides)
    return cfg


def snapshot_config(cfg, out_path):
    """把生效配置整份写出(供 run 产出目录留档;快照文件名已被密钥扫描拦截规则覆盖)。"""
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(copy.deepcopy(cfg), f, allow_unicode=True, sort_keys=False)


def structure_diff(a, b, prefix=""):
    """递归比较两份配置的键结构(不比值),返回差异描述列表;空列表=结构一致。
    用途:config.yaml 与 config.example.yaml 的同步校验(旧项目"example漂移"之债)。"""
    diffs = []
    a_keys, b_keys = set(a or {}), set(b or {})
    for k in sorted(a_keys - b_keys):
        diffs.append("仅左侧存在: %s%s" % (prefix, k))
    for k in sorted(b_keys - a_keys):
        diffs.append("仅右侧存在: %s%s" % (prefix, k))
    for k in sorted(a_keys & b_keys):
        va, vb = a[k], b[k]
        if isinstance(va, dict) and isinstance(vb, dict):
            diffs.extend(structure_diff(va, vb, prefix="%s%s." % (prefix, k)))
        elif isinstance(va, dict) != isinstance(vb, dict):
            diffs.append("类型不一致(dict vs 标量): %s%s" % (prefix, k))
    return diffs


def check_example_sync(config_path=None, example_path=None):
    """校验 config.yaml 与 config.example.yaml 结构一致;不一致返回差异列表。"""
    with open(config_path or DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with open(example_path or EXAMPLE_CONFIG_PATH, encoding="utf-8") as f:
        example = yaml.safe_load(f)
    return structure_diff(cfg, example)


if __name__ == "__main__":
    import json
    print(json.dumps(load_config(), ensure_ascii=False, indent=2))
