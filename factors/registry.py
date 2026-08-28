# coding: utf-8
"""因子注册表(factors/registry.yaml):元数据与实现分离,YAML 是唯一权威登记表,代码只读;
检验管线只能通过 write_back 写回裁决类字段,公式/假设等定义字段不许由程序改。

五要素必填(SOP S2 经济学原理必填):id / formula / direction / hypothesis / category。
状态机:candidate → tested → active | tested_weak | rejected;rejected / tested_weak 永不删除(防重复发明)。
role:candidate(普通候选)/ positive_control(阳性对照:已知因子)/ negative_control(阴性对照:随机因子)。
"""
import os
from collections import OrderedDict

import yaml

from core.config import ROOT

DEFAULT_PATH = os.path.join(ROOT, "factors", "registry.yaml")
REQUIRED = ("id", "formula", "direction", "hypothesis", "category")
DIRECTIONS = ("higher_better", "lower_better", "to_be_tested")
STATUSES = ("candidate", "tested", "active", "tested_weak", "rejected")
ROLES = ("candidate", "positive_control", "negative_control")
WRITABLE = ("status", "direction", "hypothesis", "test_report", "data_version", "oos_evaluated",
            "redundant_with", "control_reference", "notes")


class RegistryError(ValueError):
    pass


def _validate(entry):
    missing = [k for k in REQUIRED if not entry.get(k)]
    if missing:
        raise RegistryError("因子 %r 缺五要素: %s" % (entry.get("id"), ", ".join(missing)))
    entry.setdefault("status", "candidate")
    entry.setdefault("role", "candidate")
    if entry["direction"] not in DIRECTIONS:
        raise RegistryError("因子 %s direction 非法: %r(应为 %s)" % (entry["id"], entry["direction"], "/".join(DIRECTIONS)))
    if entry["status"] not in STATUSES:
        raise RegistryError("因子 %s status 非法: %r(应为 %s)" % (entry["id"], entry["status"], "/".join(STATUSES)))
    if entry["role"] not in ROLES:
        raise RegistryError("因子 %s role 非法: %r(应为 %s)" % (entry["id"], entry["role"], "/".join(ROLES)))
    return entry


def _read(path):
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise RegistryError("注册表应为条目列表: %s" % path)
    return raw


def load_registry(path=None):
    """→ OrderedDict(id → entry),保持文件顺序;缺要素/非法枚举/重复 id → RegistryError。"""
    out = OrderedDict()
    for entry in _read(path or DEFAULT_PATH):
        entry = _validate(dict(entry))
        if entry["id"] in out:
            raise RegistryError("因子 id 重复: %s" % entry["id"])
        out[entry["id"]] = entry
    return out


def _header(path):
    """文件头的注释块(首个条目之前的 # 行与空行),写回时原样保留。"""
    lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                lines.append(line)
            else:
                break
    return "".join(lines)


def write_back(path, factor_id, updates):
    """管线写回裁决字段(只允许 WRITABLE 列),保持条目顺序、其余字段与文件头注释原样。"""
    bad = [k for k in updates if k not in WRITABLE]
    if bad:
        raise RegistryError("不允许由管线写回的字段: %s(定义类字段只能人工改)" % ", ".join(bad))
    header = _header(path)
    raw = _read(path)
    for entry in raw:
        if entry.get("id") == factor_id:
            entry.update(updates)
            _validate(dict(entry))
            break
    else:
        raise RegistryError("注册表里没有因子: %s" % factor_id)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(raw, f, allow_unicode=True, sort_keys=False)
