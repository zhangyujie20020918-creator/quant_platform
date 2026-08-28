# coding: utf-8
"""因子检验管线(资产无关):批前声明 → 样本内/外统计 → BH → 对照组 → 裁决 → 写回注册表。

- 判据先于数据:declaration() 只读 config.protocol,调用方须在算任何数字之前把它写进报告首节。
- 样本外每因子只评估一次:注册表 oos_evaluated 非空的因子不再算样本外,沿用终审 status。
- 对照组失败(ControlFailed)→ 本批作废:不写回注册表、不出裁决。
- 方向 to_be_tested 的因子:由样本内 IC 符号判定并写回,hypothesis 追加判定日期(禁止事后补叙)。
"""
import datetime as _dt

import numpy as np
import pandas as pd

from core.config import get
from factors.ic import ic_series, ic_stats, ic_ttest
from factors.multiple_comparison import benjamini_hochberg
from factors.quantiles import monotonicity, quantile_returns, top_group_turnover
from factors.registry import load_registry, write_back
from factors.verdict import check_controls, decide

THRESHOLD_KEYS = ("ic_min", "icir_min", "monotonicity_min", "oos_retention_min", "bh_alpha",
                  "positive_control_tolerance", "redundancy_corr_max")


def declaration(cfg, n_candidates, today=None):
    """批前声明:本批阈值 + 样本切分 + 候选总数(供多重比较校正)。"""
    p = get(cfg, "protocol")
    return {
        "declared_at": (today or _dt.date.today()).isoformat(),
        "n_candidates": int(n_candidates),
        "thresholds": {k: p[k] for k in THRESHOLD_KEYS},
        "in_sample": [str(x) for x in p["in_sample"]],
        "out_of_sample": [str(x) for x in p["out_of_sample"]],
        "signal_freq": p["signal_freq"], "holding_days": int(p["holding_days"]), "n_quantiles": int(p["n_quantiles"]),
    }


def _slice(panel, rng):
    s, e = pd.Timestamp(rng[0]), pd.Timestamp(rng[1])
    return panel.loc[(panel.index >= s) & (panel.index <= e)]


def evaluate(factor_panel, fwd_panel, cfg, skip_oos=False):
    """单因子统计:样本内 IC/ICIR/t/p/分组单调/换手 + 样本外 IC/ICIR(skip_oos 时为 NaN)。"""
    p = get(cfg, "protocol")
    nq = int(p["n_quantiles"])
    f_is = _slice(factor_panel, p["in_sample"])
    ic_is = ic_series(f_is, fwd_panel)
    st = ic_stats(ic_is)
    t, pv = ic_ttest(ic_is)
    qr = quantile_returns(f_is, fwd_panel, nq)
    to = top_group_turnover(f_is, nq)
    row = {"ic_is": st["ic_mean"], "icir_is": st["icir"], "n_is": st["n"], "positive_rate_is": st["positive_rate"],
           "t_is": t, "p_is": pv, "monotonicity": monotonicity(qr),
           "turnover": float(to.mean()) if len(to) else np.nan,
           "quantile_returns_is": {int(k): float(v) for k, v in qr.mean().items()} if len(qr) else {}}
    if skip_oos:
        row.update({"ic_oos": np.nan, "icir_oos": np.nan, "n_oos": 0})
    else:
        so = ic_stats(ic_series(_slice(factor_panel, p["out_of_sample"]), fwd_panel))
        row.update({"ic_oos": so["ic_mean"], "icir_oos": so["icir"], "n_oos": so["n"]})
    return row


def _rank_corr(a, b):
    both = pd.concat([a.stack(), b.stack()], axis=1, keys=["a", "b"]).dropna()
    if len(both) < 3:
        return np.nan
    return float(both["a"].corr(both["b"], method="spearman"))


def _nan(v):
    return v is None or (isinstance(v, float) and np.isnan(v))


def run_batch(panels, fwd_panel, registry_path, cfg, report, data_version, today=None):
    """panels: {factor_id: DataFrame(信号日 × symbol)};fwd_panel: 同口径前瞻收益。
    返回 {"declaration", "rows": {id: 统计+verdict}, "controls": {id: 说明}, "redundancy": {id: [ids]}}。"""
    p = get(cfg, "protocol")
    today = today or _dt.date.today()
    reg = load_registry(registry_path)
    missing = [fid for fid in panels if fid not in reg]
    if missing:
        raise KeyError("面板里有未登记的因子: %s" % ", ".join(missing))
    decl = declaration(cfg, n_candidates=sum(1 for fid in panels if reg[fid]["role"] == "candidate"), today=today)

    rows = {}
    for fid, panel in panels.items():
        entry = reg[fid]
        skip = bool(entry.get("oos_evaluated"))
        row = evaluate(panel, fwd_panel, cfg, skip_oos=skip)
        row.update({"role": entry["role"], "oos_skipped": skip, "direction_registered": entry["direction"]})
        rows[fid] = row

    # BH:候选 + 阳性对照一起校正;阴性对照单独用未校正 p(更严,更容易暴露泄漏)
    bh = benjamini_hochberg({fid: r["p_is"] for fid, r in rows.items() if r["role"] != "negative_control"},
                            fdr=float(p["bh_alpha"]))
    for fid, r in rows.items():
        if r["role"] == "negative_control":
            r["p_adj"] = r["p_is"]
            r["bh_reject"] = (not _nan(r["p_is"])) and r["p_is"] < float(p["bh_alpha"])
        else:
            r["p_adj"], r["bh_reject"] = bh[fid]["p_adj"], bh[fid]["reject"]
        r["verdict"] = reg[fid]["status"] if r["oos_skipped"] else decide(r, cfg)

    controls = {fid: (r["role"], r["verdict"], {"ic_is": r["ic_is"], "reference": reg[fid].get("control_reference"),
                                                "direction": reg[fid]["direction"]})
                for fid, r in rows.items() if r["role"] != "candidate"}
    notes = check_controls(controls, cfg)          # 失败即抛,本批作废

    # 冗余:与本批裁决后为 active 的其他因子的秩相关
    active = [fid for fid, r in rows.items() if r["verdict"] == "active"]
    redundancy = {}
    for fid in panels:
        reds = []
        for other in active:
            if other == fid:
                continue
            rho = _rank_corr(panels[fid], panels[other])
            if not _nan(rho) and abs(rho) > float(p["redundancy_corr_max"]):
                reds.append(other)
        redundancy[fid] = reds
        rows[fid]["redundant_with"] = reds

    # 写回
    for fid, r in rows.items():
        entry = reg[fid]
        updates = {"test_report": report, "data_version": data_version, "redundant_with": r["redundant_with"]}
        if not r["oos_skipped"]:
            updates["status"] = r["verdict"]
            updates["oos_evaluated"] = today.isoformat()
            if entry["direction"] == "to_be_tested" and entry["role"] == "candidate" and not _nan(r["ic_is"]):
                updates["direction"] = "lower_better" if r["ic_is"] < 0 else "higher_better"
                updates["hypothesis"] = "%s;方向由样本内IC判定于%s(IC_is=%.4f)" % (entry["hypothesis"], today.isoformat(), r["ic_is"])
        if entry["role"] == "positive_control" and _nan(entry.get("control_reference")) and not _nan(r["ic_is"]):
            updates["control_reference"] = float(r["ic_is"])
        write_back(registry_path, fid, updates)
    return {"declaration": decl, "rows": rows, "controls": notes, "redundancy": redundancy}
