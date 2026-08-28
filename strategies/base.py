# coding: utf-8
"""策略两原型基类(SOP S3:原型先归类——截面选券 / 时序配置)。

契约:`signal(asof, ctx) -> {symbol: target_weight}`,**纯逻辑、引擎无关**——同一 signal() 在回测(RQAlphaContext)
与出信号(StoreContext)两种 ctx 下必须给出相同选券(测试锁死)。调仓日一律来自 core.calendar(禁止各策略自算)。
ctx 接口(SignalContext):constituents(asof) / is_st(symbol, asof) / closes(symbol, asof, n)。
"""


class Strategy:
    type = None

    def __init__(self, package):
        self.package = package
        self.id = package.id
        self.config = package.config
        self.params = dict(self.config.get("params") or {})
        self.benchmark = list(self.config.get("benchmark") or [])
        self.risk = dict(self.config.get("risk") or {})

    def signal(self, asof, ctx):
        """→ {symbol: target_weight};未列出的标的目标权重为 0。"""
        raise NotImplementedError

    def rebalance_days(self, cal, start, end):
        return cal.rebalance_dates(start, end, self.params.get("rebalance", "monthly_first"))


class CrossSectionalStrategy(Strategy):
    """截面选券:在 universe(PIT)内打分选券。"""
    type = "cross_sectional"


class TimeSeriesStrategy(Strategy):
    """时序配置:在固定资产清单上分配权重(择时/风险平价等)。"""
    type = "time_series"
