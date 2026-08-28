# coding: utf-8
"""裁决规则:阈值全部来自 cfg.protocol;四类结论 active / tested_weak / rejected;对照组失败报错。"""
import numpy as np
import pytest

from factors.verdict import ControlFailed, check_controls, decide

CFG = {"protocol": {"ic_min": 0.03, "icir_min": 0.3, "monotonicity_min": 0.8, "oos_retention_min": 0.5,
                    "bh_alpha": 0.05, "positive_control_tolerance": 0.4, "redundancy_corr_max": 0.6}}


def _row(**kw):
    base = {"ic_is": 0.05, "icir_is": 0.5, "monotonicity": 0.9, "ic_oos": 0.04, "bh_reject": True}
    base.update(kw)
    return base


def test_all_criteria_met_is_active():
    assert decide(_row(), CFG) == "active"


@pytest.mark.parametrize("kw", [
    dict(icir_is=0.2), dict(monotonicity=0.5), dict(ic_oos=-0.04), dict(ic_oos=0.01), dict(bh_reject=False),
])
def test_signal_but_criteria_missed_is_tested_weak(kw):
    assert decide(_row(**kw), CFG) == "tested_weak"


def test_no_in_sample_signal_is_rejected():
    assert decide(_row(ic_is=0.01), CFG) == "rejected"


def test_negative_direction_treated_symmetrically():
    assert decide(_row(ic_is=-0.05, icir_is=-0.5, monotonicity=-0.9, ic_oos=-0.04), CFG) == "active"


def test_missing_values_never_active():
    assert decide(_row(ic_oos=np.nan), CFG) != "active"


# ---------- 对照组 ----------

def test_negative_control_must_not_be_active():
    with pytest.raises(ControlFailed):
        check_controls({"random": ("negative_control", "active", None)}, CFG)
    check_controls({"random": ("negative_control", "rejected", None)}, CFG)      # 正常


def test_positive_control_reproduces_reference_within_tolerance():
    # (role, verdict, {"ic_is", "reference", "direction"})
    ok = {"rev_20": ("positive_control", "active", {"ic_is": -0.05, "reference": -0.06, "direction": "lower_better"})}
    check_controls(ok, CFG)
    with pytest.raises(ControlFailed):        # 偏离基线超 40%
        check_controls({"rev_20": ("positive_control", "active",
                                   {"ic_is": -0.02, "reference": -0.06, "direction": "lower_better"})}, CFG)
    with pytest.raises(ControlFailed):        # 方向与登记相反
        check_controls({"rev_20": ("positive_control", "active",
                                   {"ic_is": 0.05, "reference": None, "direction": "lower_better"})}, CFG)
    with pytest.raises(ControlFailed):        # 无基线时至少要有信号
        check_controls({"rev_20": ("positive_control", "rejected",
                                   {"ic_is": -0.01, "reference": None, "direction": "lower_better"})}, CFG)
