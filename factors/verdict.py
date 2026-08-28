# coding: utf-8
"""裁决规则(防挖矿协议可测试实现;阈值全部来自 config.protocol,本文件不出现数字)。

active ⇔ 样本内 |IC| ≥ ic_min ∧ |ICIR| ≥ icir_min ∧ |单调性| ≥ monotonicity_min ∧ 样本外 IC 同号
        ∧ |IC_oos| ≥ oos_retention_min × |IC_is| ∧ BH 校正后显著。
样本内有信号但其余不满足 → tested_weak;样本内无信号 → rejected。正负向对称(按绝对值判)。
对照组:阴性对照(随机因子)判 active → 本批作废;阳性对照方向须与登记一致,有基线时须复现到容差内,
无基线时至少要有样本内信号——不达标同样本批作废(ControlFailed)。
"""
import numpy as np

from core.config import get


class ControlFailed(RuntimeError):
    pass


def _nan(v):
    return v is None or (isinstance(v, float) and np.isnan(v))


def decide(row, cfg):
    """row: {ic_is, icir_is, monotonicity, ic_oos, bh_reject} → 'active' | 'tested_weak' | 'rejected'。"""
    p = get(cfg, "protocol")
    ic_is = row.get("ic_is")
    if _nan(ic_is) or abs(ic_is) < float(p["ic_min"]):
        return "rejected"
    icir, mono, ic_oos = row.get("icir_is"), row.get("monotonicity"), row.get("ic_oos")
    if any(_nan(v) for v in (icir, mono, ic_oos)) or not row.get("bh_reject"):
        return "tested_weak"
    if abs(icir) < float(p["icir_min"]) or abs(mono) < float(p["monotonicity_min"]):
        return "tested_weak"
    if (ic_is > 0) != (ic_oos > 0) or abs(ic_oos) < float(p["oos_retention_min"]) * abs(ic_is):
        return "tested_weak"
    return "active"


def expected_sign(direction):
    return {"higher_better": 1, "lower_better": -1}.get(direction, 0)


def check_controls(controls, cfg):
    """controls: {id: (role, verdict, info)};info 对阳性对照 = {ic_is, reference, direction}。
    通过 → 返回 {id: 说明};任一对照失败 → ControlFailed(本批检验作废)。"""
    p = get(cfg, "protocol")
    tol, ic_min = float(p["positive_control_tolerance"]), float(p["ic_min"])
    notes = {}
    for fid, (role, verdict, info) in controls.items():
        if role == "negative_control":
            if verdict == "active":
                raise ControlFailed("阴性对照 %s 被判 active:管线或数据有未来函数/泄漏,本批作废" % fid)
            notes[fid] = "阴性对照判 %s,正常" % verdict
        elif role == "positive_control":
            ic, ref, direction = info["ic_is"], info.get("reference"), info.get("direction")
            if _nan(ic):
                raise ControlFailed("阳性对照 %s 无样本内 IC" % fid)
            sign = expected_sign(direction)
            if sign and np.sign(ic) != sign:
                raise ControlFailed("阳性对照 %s 方向与登记(%s)相反:IC_is=%.4f" % (fid, direction, ic))
            if ref is None or _nan(ref):
                if abs(ic) < ic_min:
                    raise ControlFailed("阳性对照 %s 首次建立基线但无信号:|IC_is|=%.4f < %.3f" % (fid, abs(ic), ic_min))
                notes[fid] = "阳性对照首次运行,基线 IC_is=%.4f 建立" % ic
            else:
                if abs(ic - ref) > tol * abs(ref):
                    raise ControlFailed("阳性对照 %s 未复现基线:IC_is=%.4f vs 基线 %.4f(容差 ±%.0f%%)" % (fid, ic, ref, tol * 100))
                notes[fid] = "阳性对照复现:IC_is=%.4f vs 基线 %.4f" % (ic, ref)
    return notes
