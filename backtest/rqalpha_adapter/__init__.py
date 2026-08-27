# coding: utf-8
"""RQAlpha 数据源适配层:让 RQAlpha 引擎消费我们的 store(卡3;不用 ricequant bundle)。

依赖方向:backtest ← instruments ← data ← core(蓝图第三节);本包只 import store/规则表,不碰 fetcher。
"""
