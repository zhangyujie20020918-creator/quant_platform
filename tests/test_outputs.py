# coding: utf-8
import os

import pytest

from core.outputs import report_dir, reports_root, run_dir


def test_report_and_run_dir_layout(tmp_path):
    root = str(tmp_path)
    d = report_dir("数据体检", date="2026-08-24", root=root)
    assert os.path.isdir(d)
    assert d.endswith(os.path.join("reports", "2026-08-24_数据体检"))
    r = run_dir("数据体检", "smoke", date="2026-08-24", root=root)
    assert os.path.isdir(r)
    assert os.path.basename(r) == "smoke_runs"        # 统一 *_runs 后缀,gitignore一条规则排除
    assert os.path.dirname(r) == d
    assert run_dir("数据体检", "smoke", date="2026-08-24", root=root) == r   # 幂等


def test_default_date_and_cfg_reports_dir(tmp_path):
    cfg = {"meta": {"reports_dir": "out"}}
    d = report_dir("topic x", cfg=cfg, root=str(tmp_path))
    assert os.path.basename(os.path.dirname(d)) == "out"
    assert os.path.basename(d).endswith("_topic_x")
    assert reports_root(cfg, root=str(tmp_path)) == os.path.join(str(tmp_path), "out")


@pytest.mark.parametrize("bad", ["a/b", "a\\b", "", "   ", "..\\x"])
def test_rejects_unsafe_names(tmp_path, bad):
    with pytest.raises(ValueError):
        report_dir(bad, root=str(tmp_path))
    with pytest.raises(ValueError):
        run_dir("ok", bad, root=str(tmp_path))
