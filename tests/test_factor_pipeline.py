# coding: utf-8
"""检验管线:批前声明先于数字;样本内外切分;BH;对照组;裁决;方向写回;样本外只评估一次。合成面板,不触网。"""
import numpy as np
import pandas as pd
import pytest
import yaml

from factors.pipeline import declaration, evaluate, run_batch
from factors.registry import load_registry

CFG = {"protocol": {
    "ic_min": 0.03, "icir_min": 0.3, "monotonicity_min": 0.8, "oos_retention_min": 0.5, "bh_alpha": 0.05,
    "positive_control_tolerance": 0.4, "redundancy_corr_max": 0.6,
    "signal_freq": "monthly_first", "holding_days": 20, "n_quantiles": 5,
    "in_sample": ["2015-01-01", "2018-12-31"], "out_of_sample": ["2019-01-01", "2020-12-31"],
    "min_periods_ratio": 0.6, "negative_control_seed": 1, "alphalens_periods": [1, 5, 20]}}

SIGNAL_DATES = pd.bdate_range("2015-01-01", "2020-12-31", freq="BMS")     # 月初信号日
SYMS = [f"S{i:03d}" for i in range(120)]      # 截面够大,噪声因子的 |IC| 才稳定落在 ic_min 之下


def _world(seed=0):
    rng = np.random.default_rng(seed)
    fwd = pd.DataFrame(rng.normal(0, 0.05, (len(SIGNAL_DATES), len(SYMS))), index=SIGNAL_DATES, columns=SYMS)
    strong = -fwd + rng.normal(0, 0.02, fwd.shape)          # 强负向信号(lower_better)
    noise = pd.DataFrame(rng.normal(0, 1, fwd.shape), index=SIGNAL_DATES, columns=SYMS)
    return fwd, strong, noise


def test_declaration_lists_thresholds_split_and_batch_size():
    d = declaration(CFG, n_candidates=3)
    assert d["n_candidates"] == 3 and d["in_sample"] == ["2015-01-01", "2018-12-31"]
    assert d["thresholds"]["ic_min"] == 0.03 and "holding_days" in d


def test_evaluate_splits_in_and_out_of_sample():
    fwd, strong, _ = _world()
    row = evaluate(strong, fwd, CFG)
    assert row["n_is"] == 48 and row["n_oos"] == 24
    assert row["ic_is"] < -0.5 and row["ic_oos"] < -0.5 and row["monotonicity"] == pytest.approx(-1.0)
    assert 0 <= row["turnover"] <= 1 and row["p_is"] < 1e-6


def test_run_batch_verdicts_controls_and_direction_writeback(tmp_path):
    fwd, strong, noise = _world()
    reg_path = tmp_path / "registry.yaml"
    reg_path.write_text(yaml.safe_dump([
        {"id": "strong", "formula": "-fwd", "direction": "to_be_tested", "hypothesis": "h", "category": "c"},
        {"id": "noise", "formula": "noise", "direction": "higher_better", "hypothesis": "h", "category": "c"},
        {"id": "known", "formula": "-fwd", "direction": "lower_better", "hypothesis": "h", "category": "c",
         "role": "positive_control"},
        {"id": "random", "formula": "rng", "direction": "to_be_tested", "hypothesis": "h", "category": "c",
         "role": "negative_control"},
    ], allow_unicode=True), encoding="utf-8")
    panels = {"strong": strong, "noise": noise, "known": strong * 0.9, "random": noise * 2}
    out = run_batch(panels, fwd, str(reg_path), CFG, report="r.md", data_version="2026-08-26")
    rows = out["rows"]
    assert rows["strong"]["verdict"] == "active" and rows["noise"]["verdict"] == "rejected"
    assert rows["random"]["verdict"] != "active"
    assert out["controls"]["known"].startswith("阳性对照首次运行")
    reg = load_registry(str(reg_path))
    assert reg["strong"]["status"] == "active" and reg["strong"]["direction"] == "lower_better"   # 方向由样本内 IC 判定
    assert "方向由样本内IC判定于" in reg["strong"]["hypothesis"]
    assert reg["strong"]["oos_evaluated"] and reg["strong"]["test_report"] == "r.md"
    assert reg["known"]["control_reference"] == pytest.approx(rows["known"]["ic_is"])
    assert reg["noise"]["status"] == "rejected"
    assert reg["random"]["direction"] == "to_be_tested"                  # 阴性对照不判方向
    # 冗余标注:known 与 strong 高度相关 → redundant_with 互标
    assert "strong" in reg["known"]["redundant_with"]


def test_out_of_sample_evaluated_only_once(tmp_path):
    fwd, strong, _ = _world()
    reg_path = tmp_path / "registry.yaml"
    reg_path.write_text(yaml.safe_dump([
        {"id": "strong", "formula": "-fwd", "direction": "lower_better", "hypothesis": "h", "category": "c",
         "status": "active", "oos_evaluated": "2026-01-01", "test_report": "old.md"},
    ]), encoding="utf-8")
    out = run_batch({"strong": strong}, fwd, str(reg_path), CFG, report="new.md", data_version="x")
    row = out["rows"]["strong"]
    assert row["oos_skipped"] and np.isnan(row["ic_oos"]) and row["verdict"] == "active"    # 沿用终审
    assert load_registry(str(reg_path))["strong"]["oos_evaluated"] == "2026-01-01"          # 不覆盖


def test_negative_control_active_aborts_batch(tmp_path):
    fwd, strong, _ = _world()
    reg_path = tmp_path / "registry.yaml"
    reg_path.write_text(yaml.safe_dump([
        {"id": "leak", "formula": "x", "direction": "to_be_tested", "hypothesis": "h", "category": "c",
         "role": "negative_control"},
    ]), encoding="utf-8")
    from factors.verdict import ControlFailed
    with pytest.raises(ControlFailed):
        run_batch({"leak": strong}, fwd, str(reg_path), CFG, report="r.md", data_version="x")
    assert load_registry(str(reg_path))["leak"]["status"] == "candidate"                     # 作废不写回
