# coding: utf-8
import os
import textwrap

import pytest

from core.config import (DEFAULT_CONFIG_PATH, apply_overrides, check_example_sync, get,
                         load_config, structure_diff)


def _write(tmp_path, text):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(p)


SAMPLE = """
    a:
      b: 1
      flag: true
    s: hello
"""


def test_load_and_override_returns_independent_copies(tmp_path):
    p = _write(tmp_path, SAMPLE)
    cfg = load_config(p)
    assert cfg["a"]["b"] == 1
    cfg2 = load_config(p, overrides=["a.b=2", "a.flag=false", "s=world"])
    assert cfg2["a"]["b"] == 2 and cfg2["a"]["flag"] is False and cfg2["s"] == "world"
    assert load_config(p)["a"]["b"] == 1


def test_override_rejects_unknown_path_and_bad_format(tmp_path):
    p = _write(tmp_path, SAMPLE)
    with pytest.raises(KeyError):
        load_config(p, overrides=["a.zzz=1"])
    with pytest.raises(KeyError):
        load_config(p, overrides=["nope.b=1"])
    with pytest.raises(ValueError):
        load_config(p, overrides=["a.b"])
    assert apply_overrides({"k": 1}, None) == {"k": 1}


def test_get_dot_path():
    cfg = {"a": {"b": {"c": 3}}}
    assert get(cfg, "a.b.c") == 3
    assert get(cfg, "a.x", default=None) is None
    assert get(cfg, "a.b.c.d", default="dflt") == "dflt"
    with pytest.raises(KeyError):
        get(cfg, "a.x")


def test_structure_diff_reports_keys_not_values():
    a = {"m": {"x": 1, "y": 2}, "p": 1}
    b = {"m": {"x": 9}, "q": 2}
    diffs = structure_diff(a, b)
    assert any("m.y" in d for d in diffs)
    assert any(d.endswith(" p") for d in diffs)
    assert any(d.endswith(" q") for d in diffs)
    assert structure_diff(a, a) == []
    assert structure_diff({"k": {"x": 1}}, {"k": {"x": 999}}) == []
    assert any("类型不一致" in d for d in structure_diff({"k": {"z": 1}}, {"k": 1}))


def test_repo_config_matches_example():
    """真实仓库:本机存在 config.yaml 时,其结构必须与 config.example.yaml 一致(防漂移)。"""
    if not os.path.exists(DEFAULT_CONFIG_PATH):
        pytest.skip("本机无 config.yaml")
    assert check_example_sync() == []
