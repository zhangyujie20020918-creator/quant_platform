# coding: utf-8
"""示踪弹编排(tools/tracer.py):失败不中断、逐环节记录、报告落盘;用假 runner,不跑任何长任务。"""
import os

from tools.tracer import Stage, build_stages, run_stages, write_trace


def test_run_stages_continues_after_failure_and_records_everything():
    calls = []

    def fake_runner(stage):
        calls.append(stage.name)
        if stage.name == "S2":
            return 1, "boom"
        return 0, "ok %s" % stage.name

    stages = [Stage("S0", "检查", ["python", "-c", "pass"]), Stage("S2", "因子", ["python", "-m", "x"]),
              Stage("S5", "信号", ["python", "-m", "y"])]
    records = run_stages(stages, runner=fake_runner)
    assert calls == ["S0", "S2", "S5"]                                 # 失败后继续
    assert [r["name"] for r in records] == ["S0", "S2", "S5"]
    assert records[1]["passed"] is False and records[1]["output"] == "boom" and records[0]["passed"] is True
    assert all(r["seconds"] >= 0 for r in records)


def test_stage_with_python_check_callable():
    stage = Stage("S0", "想法登记", check=lambda: (True, "找到 toy_lowvol"))
    records = run_stages([stage], runner=None)
    assert records[0]["passed"] and "toy_lowvol" in records[0]["output"]


def test_build_stages_has_six_in_sop_order_and_skip_works():
    stages = build_stages(date="2026-08-28", python="py")
    assert [s.name for s in stages] == ["S0", "S1", "S2", "S3/S4", "S5", "面板"]
    assert stages[2].cmd[:3] == ["py", "-m", "factors.run_factor_tests"] and "--date" in stages[2].cmd
    kept = build_stages(date="2026-08-28", python="py", skip={"S2", "S3/S4"})
    assert [s.name for s in kept] == ["S0", "S1", "S5", "面板"]


def test_write_trace_reports_overall_verdict(tmp_path):
    records = [{"name": "S0", "title": "想法登记", "passed": True, "seconds": 0.1, "output": "ok", "cmd": ""},
               {"name": "S2", "title": "因子", "passed": False, "seconds": 5.0, "output": "boom", "cmd": "py -m x"}]
    path = write_trace(str(tmp_path), records, date="2026-08-28")
    text = open(path, encoding="utf-8").read()
    assert os.path.basename(path) == "trace.md" and "不通过" in text and "S2" in text and "boom" in text
    path_ok = write_trace(str(tmp_path / "ok"), [dict(records[0])], date="2026-08-28")
    assert "全部通过" in open(path_ok, encoding="utf-8").read()
