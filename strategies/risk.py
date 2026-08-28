# coding: utf-8
"""风控参数(策略包 risk 小节;机制在此,数值在包):max_weight 单票封顶(超出部分留现金,不再分配)、
max_positions 按权重从高到低截断。回测与出信号共用同一入口。"""


def apply_risk(weights, risk):
    max_w = float(risk.get("max_weight", 1.0))
    max_n = risk.get("max_positions")
    items = sorted(((k, float(v)) for k, v in weights.items() if v and v > 0), key=lambda kv: -kv[1])   # 稳定排序:并列保持策略顺序
    if max_n:
        items = items[:int(max_n)]
    return {k: min(v, max_w) for k, v in items}
