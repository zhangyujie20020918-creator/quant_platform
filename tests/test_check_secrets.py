# coding: utf-8
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("check_secrets", os.path.join(ROOT, "tools", "check_secrets.py"))
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)


def test_hex_rule_passes_commit_id_blocks_token():
    assert cs.scan_content("see commit " + "a" * 40) == []
    hits = cs.scan_content("token: " + "b" * 60)
    assert len(hits) == 1 and "60位" in hits[0]
    assert "b" * 13 not in hits[0]          # 报错信息不泄露完整值


def test_forbidden_filenames_any_directory():
    assert cs.forbidden_filename("x/y/config.yaml")
    assert cs.forbidden_filename("reports\\a\\config.snapshot.yaml")
    assert not cs.forbidden_filename("config.example.yaml")


def test_scan_directory(tmp_path):
    (tmp_path / "ok.md").write_text("fine " + "c" * 40, encoding="utf-8")
    (tmp_path / "bad.txt").write_text("k=" + "d" * 45, encoding="utf-8")
    (tmp_path / "config.yaml").write_text("x: 1", encoding="utf-8")
    (tmp_path / "bin.dat").write_bytes(b"\xff\xfe" + b"e" * 50)
    errs = cs.scan_directory(str(tmp_path))
    assert len(errs) == 2
    assert any("bad.txt" in e for e in errs)
    assert any("config.yaml" in e for e in errs)
