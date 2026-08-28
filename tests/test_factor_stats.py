# coding: utf-8
"""因子检验统计(资产无关):前瞻收益 T+1 锁死、IC/ICIR/t 检验、BH 多重比较校正。合成面板,手工可验。"""
import numpy as np
import pandas as pd
import pytest

from factors.forward_returns import forward_returns
from factors.ic import ic_series, ic_stats, ic_ttest
from factors.multiple_comparison import benjamini_hochberg

DATES = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"])


def _panel(values, symbols=("A", "B")):
    return pd.DataFrame(values, index=DATES, columns=list(symbols))


# ---------- 前瞻收益:信号日 T → open[T+1+H]/open[T+1] − 1 ----------

def test_forward_return_uses_next_open_to_next_plus_h_open():
    opens = _panel([[10, 20], [11, 20], [12, 20], [13, 20], [14, 20], [15, 20]])
    fr = forward_returns(opens, holding_days=2)
    # T=01-05:买 01-06 开 11,卖 01-08 开 13 → 13/11−1
    assert fr.loc["2026-01-05", "A"] == pytest.approx(13 / 11 - 1)
    assert fr.loc["2026-01-05", "B"] == pytest.approx(0.0)
    # 末尾拿不到未来数据 → NaN(01-08 起:需要 01-11 之后的开盘)
    assert np.isnan(fr.loc["2026-01-08", "A"]) and np.isnan(fr.loc["2026-01-12", "A"])


def test_forward_return_invalid_price_is_nan_not_inf():
    opens = _panel([[10, 0.0], [11, 0.0], [12, 5.0], [13, 5.0], [14, 5.0], [15, 5.0]])
    fr = forward_returns(opens, holding_days=1)
    assert np.isnan(fr.loc["2026-01-05", "B"])          # 买入价 0(停牌)→ NaN
    assert fr.loc["2026-01-07", "B"] == pytest.approx(0.0)


# ---------- IC ----------

def test_ic_series_is_daily_spearman_and_skips_small_cross_sections():
    f = pd.DataFrame({"A": [1, 1, 1], "B": [2, 2, np.nan], "C": [3, 3, 3]}, index=DATES[:3])
    r = pd.DataFrame({"A": [0.1, 0.3, 0.1], "B": [0.2, 0.2, 0.2], "C": [0.3, 0.1, 0.3]}, index=DATES[:3])
    ic = ic_series(f, r)
    assert ic.loc[DATES[0]] == pytest.approx(1.0) and ic.loc[DATES[1]] == pytest.approx(-1.0)
    assert DATES[2] not in ic.index                       # 该日只剩 2 个样本 → 跳过


def test_ic_stats_and_ttest():
    ic = pd.Series([0.05, 0.03, 0.04, -0.01, 0.06])
    st = ic_stats(ic)
    assert st["ic_mean"] == pytest.approx(0.034) and st["n"] == 5
    assert st["icir"] == pytest.approx(0.034 / ic.std())
    assert st["positive_rate"] == pytest.approx(0.8)
    t, p = ic_ttest(ic)
    assert t > 0 and 0 < p < 1
    assert ic_stats(pd.Series([], dtype=float))["n"] == 0


# ---------- BH ----------

def test_benjamini_hochberg_rejects_in_step_up_order():
    out = benjamini_hochberg({"a": 0.001, "b": 0.02, "c": 0.04, "d": 0.5, "e": np.nan}, fdr=0.05)
    # m=4:阈值 0.0125/0.025/0.0375/0.05;最大满足 p(i)≤阈值 的 i 是 c(0.04≤0.0375? 否)→ b(0.02≤0.025 是)→ a,b 显著
    assert out["a"]["reject"] and out["b"]["reject"] and not out["c"]["reject"] and not out["d"]["reject"]
    assert out["e"]["reject"] is False and np.isnan(out["e"]["p_adj"])
    assert out["a"]["p_adj"] <= out["b"]["p_adj"] <= out["c"]["p_adj"] <= out["d"]["p_adj"] <= 1.0
