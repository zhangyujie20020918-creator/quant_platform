# coding: utf-8
"""参数平原扫描的纯函数:网格解析与悬崖判定。"""
from backtest.run_sensitivity import cliff, parse_grid


def test_parse_grid():
    assert parse_grid("params.drawdown_buy=0.70,0.75,0.80") == ("params.drawdown_buy", [0.7, 0.75, 0.8])


def test_cliff_only_compares_adjacent_cells():
    cells = {(0.7, 0.4): {"cagr": 0.10}, (0.75, 0.4): {"cagr": 0.09}, (0.8, 0.4): {"cagr": 0.02},
             (0.7, 0.5): {"cagr": 0.11}}
    out = cliff(cells, 0.5)
    pairs = {(a, b) for a, b, _, _ in out}
    assert ((0.75, 0.4), (0.8, 0.4)) in pairs             # 0.09 → 0.02:差 0.07 > 0.5×0.09 → 悬崖
    assert ((0.7, 0.4), (0.75, 0.4)) not in pairs         # 平原
    assert all(sum(x != y for x, y in zip(a, b)) == 1 for a, b, _, _ in out)
