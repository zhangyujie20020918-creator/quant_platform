# 回测报告 · toy_lowvol(沪深300 低波20 月频(玩具策略,仅验证管道))

区间 2011-06-01 → 2022-06-30;初始资金 1000000;universe {'index': '000300.SH'};基准 000300.SH;状态 **toy**。
参数:{'n_select': 20, 'lookback': 20, 'rebalance': 'monthly_first', 'filter_st': True};风控:{'max_weight': 0.1, 'max_positions': 20};成本:品种规则表 instruments.cn_stock.costs;RQAlpha 内置涨跌停/停牌/T+1/退市清算。

| | 总收益 | 年化 | 最大回撤 | 夏普 |
|---|---|---|---|---|
| 策略 | 56.7% | 4.29% | -31.0% | 0.35 |
| 基准 | 49.3% | 3.82% | -46.7% | 0.28 |

- 信号 133 次,成交 3453 笔;RQAlpha summary:alpha 0.021779518888241332 / beta 0.5519183015452246 / 信息比率 0.2411296070319057;耗时 73s。
- 产出:`nav.csv`、`rq_runs/`(portfolio/trades/positions/summary,面板「回测浏览器」可看)。
- 局限:集合竞价撮合无滑点;结论仅对该 universe 有效;策略状态非 approved 时不构成任何投资依据。
