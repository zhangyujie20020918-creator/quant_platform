# 回测报告 · dd_rebound(深跌反弹(主板+创业板;历史高点回撤75%买、反弹到高点一半卖;两周调仓持10只))

区间 2019-01-01 → 2025-12-30;初始资金 100000;universe {'boards': ['主板', '创业板']};基准 000300.SH;状态 **research**。
参数:{'drawdown_buy': 0.75, 'recover_sell': 0.5, 'n_positions': 10, 'volume_window': 20, 'rebalance': 'biweekly_first', 'exclude_st': True};风控:{'max_weight': 0.1, 'max_positions': 10};执行:{'mode': 'next_close', 'slippage': 0};成本:{'commission_rate': 0, 'min_commission': 0.0, 'stamp_tax_sell': [], 'transfer_fee': []};RQAlpha 内置涨跌停/停牌/T+1/退市清算。

| | 总收益 | 年化 | 最大回撤 | 夏普 |
|---|---|---|---|---|
| 策略 | 6.4% | 0.92% | -48.2% | 0.15 |
| 基准 | 56.6% | 6.89% | -45.6% | 0.44 |

- 信号 180 次,成交 152 笔;RQAlpha summary:alpha -0.04265954739310629 / beta 0.7779020182014426 / 信息比率 -0.24640741904270633;耗时 139s。
- 产出:`nav.csv`、`rq_runs/`(portfolio/trades/positions/summary,面板「回测浏览器」可看)。
- 局限:集合竞价撮合无滑点;结论仅对该 universe 有效;策略状态非 approved 时不构成任何投资依据。
