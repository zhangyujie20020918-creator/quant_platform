# coding: utf-8
"""random_control:阴性对照——种子固定的标准正态噪声(有价才有值)。判 active 即说明管线/数据有泄漏。"""
import numpy as np
import pandas as pd

from core.config import get


def compute(ctx):
    close = ctx["close"]
    rng = np.random.default_rng(int(get(ctx["cfg"], "protocol.negative_control_seed")))
    noise = pd.DataFrame(rng.standard_normal(close.shape), index=close.index, columns=close.columns)
    return noise.where(close.notna())
