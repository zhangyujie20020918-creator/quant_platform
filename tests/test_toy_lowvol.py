# coding: utf-8
"""玩具策略:沪深300成分内选低波N只等权,月频。仅验证管道,无研究观点。"""
import numpy as np
import pandas as pd

from strategies.toy_lowvol import low_vol_weights


class _FakeUniverse:
    def __init__(self, mapping):
        self._m = {pd.Timestamp(k): v for k, v in mapping.items()}

    def constituents(self, asof):
        asof = pd.Timestamp(asof)
        valid = [d for d in self._m if d <= asof]
        return self._m[max(valid)] if valid else []


def _closes(dates, data):
    return pd.DataFrame(data, index=pd.to_datetime(dates))


def test_selects_lowest_vol_and_equal_weights():
    dates = pd.bdate_range("2026-01-01", periods=25).strftime("%Y-%m-%d").tolist()
    # A 平稳(低波),B 剧烈震荡(高波),C 温和
    n = len(dates)
    a = 100 + np.zeros(n)                       # 零波动
    b = 100 + 10 * ((-1) ** np.arange(n))       # 大幅震荡
    c = 100 + 0.5 * np.arange(n)                # 缓涨(低波动率)
    closes = _closes(dates, {"A": a, "B": b, "C": c})
    uni = _FakeUniverse({"2026-01-01": ["A", "B", "C"]})
    reb = [dates[-1]]
    w = low_vol_weights(reb, uni, closes, n_select=2, lookback=20)
    picked = set(w[dates[-1]].keys())
    assert "B" not in picked                    # 高波被剔除
    assert picked == {"A", "C"}
    assert all(abs(v - 0.5) < 1e-9 for v in w[dates[-1]].values())   # 等权


def test_respects_pit_universe_per_date():
    dates = pd.bdate_range("2026-01-01", periods=40).strftime("%Y-%m-%d").tolist()
    n = len(dates)
    closes = _closes(dates, {"A": 100 + np.zeros(n), "B": 100 + np.zeros(n), "C": 100 + np.zeros(n)})
    uni = _FakeUniverse({"2026-01-01": ["A", "B"], dates[25]: ["B", "C"]})
    w = low_vol_weights([dates[20], dates[-1]], uni, closes, n_select=5, lookback=10)
    assert set(w[dates[20]].keys()) == {"A", "B"}      # 早期成分
    assert set(w[dates[-1]].keys()) == {"B", "C"}      # 换成分后


def test_skips_symbols_with_insufficient_history():
    dates = pd.bdate_range("2026-01-01", periods=25).strftime("%Y-%m-%d").tolist()
    n = len(dates)
    a = 100 + np.zeros(n)
    b = np.concatenate([np.full(20, np.nan), 100 + np.arange(5) * 0.1])   # 上市不久,历史不足
    closes = _closes(dates, {"A": a, "B": b})
    uni = _FakeUniverse({"2026-01-01": ["A", "B"]})
    w = low_vol_weights([dates[-1]], uni, closes, n_select=5, lookback=20)
    assert set(w[dates[-1]].keys()) == {"A"}           # B 历史不足被跳过


def test_empty_universe_gives_empty_weights():
    dates = pd.bdate_range("2026-01-01", periods=25).strftime("%Y-%m-%d").tolist()
    closes = _closes(dates, {"A": 100 + np.zeros(len(dates))})
    uni = _FakeUniverse({})
    w = low_vol_weights([dates[-1]], uni, closes, n_select=5, lookback=20)
    assert w[dates[-1]] == {}
