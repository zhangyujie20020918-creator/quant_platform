# coding: utf-8
"""注册表:五要素必填、状态机、role 枚举;写回只改允许的字段;缺要素/非法值拒绝。"""
import pytest
import yaml

from factors.registry import RegistryError, load_registry, write_back

GOOD = [
    {"id": "vol_20", "name": "20日波动", "category": "volatility", "direction": "to_be_tested",
     "formula": "std(log ret, 20)", "hypothesis": "低波异象", "status": "candidate", "role": "candidate"},
    {"id": "rev_20", "name": "20日反转", "category": "momentum", "direction": "lower_better",
     "formula": "close_t/close_{t-20}-1", "hypothesis": "短期反转", "status": "candidate", "role": "positive_control"},
]


def _write(tmp_path, entries):
    p = tmp_path / "registry.yaml"
    p.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")
    return str(p)


def test_load_registry_returns_entries_keyed_by_id(tmp_path):
    reg = load_registry(_write(tmp_path, GOOD))
    assert list(reg) == ["vol_20", "rev_20"] and reg["rev_20"]["role"] == "positive_control"


@pytest.mark.parametrize("bad", [
    {k: v for k, v in GOOD[0].items() if k != "hypothesis"},                 # 缺要素
    dict(GOOD[0], direction="up"),                                            # 非法方向
    dict(GOOD[0], status="alive"),                                            # 非法状态
    dict(GOOD[0], role="control"),                                            # 非法角色
])
def test_load_registry_rejects_invalid_entry(tmp_path, bad):
    with pytest.raises(RegistryError):
        load_registry(_write(tmp_path, [bad]))


def test_load_registry_rejects_duplicate_ids(tmp_path):
    with pytest.raises(RegistryError):
        load_registry(_write(tmp_path, [GOOD[0], dict(GOOD[0])]))


def test_write_back_updates_only_allowed_fields_and_keeps_order(tmp_path):
    path = _write(tmp_path, GOOD)
    write_back(path, "vol_20", {"status": "active", "direction": "lower_better", "test_report": "r.md",
                                "data_version": "2026-08-26", "oos_evaluated": "2026-08-28"})
    reg = load_registry(path)
    assert reg["vol_20"]["status"] == "active" and reg["vol_20"]["oos_evaluated"] == "2026-08-28"
    assert list(reg) == ["vol_20", "rev_20"]
    with pytest.raises(RegistryError):
        write_back(path, "vol_20", {"formula": "changed"})                 # 公式不许由管线改
    with pytest.raises(RegistryError):
        write_back(path, "nope", {"status": "active"})


def test_write_back_preserves_header_comments(tmp_path):
    p = tmp_path / "registry.yaml"
    header = "# 头注释一" + chr(10) + "# 头注释二" + chr(10) + chr(10)
    p.write_text(header + yaml.safe_dump(GOOD, allow_unicode=True), encoding="utf-8")
    write_back(str(p), "vol_20", {"status": "tested"})
    text = p.read_text(encoding="utf-8")
    assert text.startswith(header) and load_registry(str(p))["vol_20"]["status"] == "tested"
