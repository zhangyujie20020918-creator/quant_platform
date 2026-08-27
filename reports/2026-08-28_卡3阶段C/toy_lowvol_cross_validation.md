# 卡3 阶段C · 玩具策略 RQAlpha 版 + 交叉验证报告(2026-08-28)

策略:000300.SH 成分(PIT)低波 20 只等权,月频(信号=月首交易日收盘,次日开盘执行),lookback=20;区间 2011-06-01 → 2022-06-30;
初始资金 100 万。**仅验证管道,不含研究观点。**

## 一、交叉验证(SOP S4:独立引擎复现)

对齐口径:佣金 0.0002 双边、无最低佣金、无印花税/过户费、无滑点、不过滤 ST;两边同一 universe(instruments.universe)、同一调仓日历(core.calendar)、同一选券函数(strategies.toy_lowvol.select_low_vol)、同一数据(store)。

| 引擎 | 总收益 | 年化 | 最大回撤 | 夏普 | 成交笔数 | 备注 |
|---|---|---|---|---|---|---|
| 自研 backtest.engine | 69.8% | 5.08% | -30.0% | 0.39 | 3809 | T收盘信号→T+1开盘,允许零股,无涨跌停/停牌拒单 |
| RQAlpha(store 数据源)对齐版 | 66.1% | 4.86% | -30.0% | 0.39 | 3489 | T+1 集合竞价,整手,涨跌停/停牌/T+1 内置拒单;133 次信号 |

- Δ年化 = **-0.22 pp**(容差 ±1.5 pp,`protocol.cross_engine_tolerance_pct`)→ **通过,互证成立**;Δ最大回撤 -0.01 pp。
- 日收益相关系数 0.9994,年化跟踪误差 0.61%。
- 已知口径差异(不视为缺陷):①RQAlpha 整手买入(每只约 0~1 手现金闲置);②涨停日 RQAlpha 拒买、跌停日拒卖,自研照成交;③退市/吸收合并标的 RQAlpha 按末价折现,自研引擎无价即按 0 计(自研局限,卡2 报告已声明);④自研买入顺序按选券波动排序逐只受现金约束,RQAlpha 版先清仓再买入。

## 二、全成本版(品种规则表成本 + ST 过滤 + RQAlpha 内置红线)

| 引擎 | 总收益 | 年化 | 最大回撤 | 夏普 | 成交笔数 | 备注 |
|---|---|---|---|---|---|---|
| RQAlpha 全成本版 | 56.7% | 4.29% | -31.0% | 0.35 | 3453 | 佣金万2/最低5元/印花税·过户费按生效日/ST 过滤 |
| 基准 000300.SH(自研 stats 口径) | 49.3% | 3.82% | -46.7% | 0.28 | - |  |

- RQAlpha summary:年化 4.29% | 基准年化 3.83% | alpha 0.0218 | beta 0.552 | 最大回撤 30.99% | 夏普 0.350 | 信息比率 0.241
- 成本影响(全成本版 vs 对齐版):年化 -0.57 pp。
- 产出:`reports\2026-08-28_卡3阶段C\toy_lowvol_navs.csv`(navs)、RQAlpha 报表 `rq_align_runs/`、`rq_full_runs/`。

## 三、A股股票红线核对(清单 instruments/cn_stock_redlines.md,验收测试 tests/test_cn_stock_redlines.py)

| 红线 | 机制 | 验收测试 | 结论 |
|---|---|---|---|
| R1 前复权正确 | bar 原始价 + adj_factor→ex_cum_factor,history_bars 按查询日重基;持仓过除权日合成 split | test_r1 / 阶段B 19 项核对 | 通过 |
| R2 涨停不可买、跌停不可卖 | limit_up/down 按品种规则表(板块/ST/生效日)算入 bar,RQAlpha price_limit 拒单 | test_r2 | 通过 |
| R3 停牌口径书面声明 | 交易日∧[首bar,数据末日]∧无行 → 停牌,RQAlpha is_trading_validator 拒单 | test_r3 | 通过 |
| R4 ST 过滤 | namechange 区间 → is_st_stock;策略层 filter_st 剔除 | test_r4 / test_st_filter_switches_pick | 通过 |
| R5 退市股在历史池 + 退市清算 | stock_basic 含退市入 instruments;退市前末日结算按末价折现(cash_return_by_stock_delisted) | test_r5 | 通过 |
| R6 T+1 | market_tplus=1(品种规则表),当日买入不可卖 | test_r6 | 通过 |
| R7 全成本 | RuleTableStockCostDecider:佣金/最低佣金/印花税/过户费全查表按生效日 | test_r7 | 通过 |

## 四、局限声明

- 集合竞价撮合不加滑点(RQAlpha 机制);日频只有收盘撮合,故 T+1 开盘执行走集合竞价。
- 上市首日(及科创/创业板前五日)涨跌停特例以"首日无限制"近似;科创板 200 股起、步长 1 的整手规则未在策略下单层处理(玩具策略买 100 的倍数)。
- 成交量上限 25%(RQAlpha 默认 volume_limit)保留;流动性冲击/滑点模型留给后续策略研究按品种配置。
- 无风险利率为 config 常数 `backtest.risk_free_rate`;RQAlpha 提示 `base.capital_gain_tax_rate` 未显式配置(默认 0,A 股个人免征)。
