# coding: utf-8
"""alphalens 薄封装:T+1 价格口径在入口锁死,全平台只能经此调用 alphalens(裸调用视为违规)。

locked_prices(opens) = open.shift(−1):alphalens 把 prices.loc[T] 当作信号日 T 的"可成交价",
我们喂 T+1 开盘,于是它算的前瞻收益 = open[T+1+h]/open[T+1] − 1,与 factors.forward_returns 同口径。
"""
import os

import matplotlib
matplotlib.use("Agg")                       # 无显示环境;必须在 pyplot 之前
import matplotlib.pyplot as plt           # noqa: E402
import pandas as pd                       # noqa: E402
from alphalens import performance, tears, utils  # noqa: E402


def locked_prices(opens):
    return opens.shift(-1)


def to_factor_series(factor_panel):
    s = factor_panel.stack()
    s.index = s.index.set_names(["date", "asset"])
    return s.dropna()


def clean_factor(factor_panel, opens, periods, quantiles, max_loss=0.35):
    return utils.get_clean_factor_and_forward_returns(to_factor_series(factor_panel), locked_prices(opens),
                                                      periods=tuple(int(x) for x in periods), quantiles=int(quantiles),
                                                      max_loss=max_loss)


def tear_sheet(factor_panel, opens, out_dir, periods=(1, 5, 20), quantiles=5, name="factor"):
    """完整 tear sheet → PNG 若干 + 分组收益/IC 两张 CSV;返回产出文件路径列表。"""
    os.makedirs(out_dir, exist_ok=True)
    data = clean_factor(factor_panel, opens, periods, quantiles)
    files = []
    mean_ret, _ = performance.mean_return_by_quantile(data, by_date=False)
    path = os.path.join(out_dir, "%s_quantile_returns.csv" % name)
    mean_ret.to_csv(path, encoding="utf-8-sig")
    files.append(path)
    ic = performance.factor_information_coefficient(data)
    path = os.path.join(out_dir, "%s_ic.csv" % name)
    pd.concat([ic.describe(), ic.mean().to_frame("mean").T, (ic.mean() / ic.std()).to_frame("icir").T]).to_csv(
        path, encoding="utf-8-sig")
    files.append(path)

    plt.close("all")
    tears.create_full_tear_sheet(data, long_short=True, group_neutral=False, by_group=False)
    for i, num in enumerate(plt.get_fignums(), start=1):
        fig = plt.figure(num)
        path = os.path.join(out_dir, "%s_tear_%02d.png" % (name, i))
        fig.savefig(path, dpi=110, bbox_inches="tight")
        files.append(path)
    plt.close("all")
    return files
