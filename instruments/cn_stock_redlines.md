# A股股票品种包 · 真实性红线清单

蓝图第七节机制:红线清单属于品种包,与品种规则表(`config instruments.cn_stock` + `instruments/cn_stock.py`)
同处登记;引擎验收测试按本清单实例化(`tests/test_cn_stock_redlines.py`,合成 store,不触网)。
SOP S4 引用的是本清单;新品种(如债ETF、可转债)挂各自清单,核心引擎零修改。

| # | 红线 | 机制(数据 + 引擎) | 验收测试 | 口径声明 / 局限 |
|---|---|---|---|---|
| R1 | 前复权正确(头号未来函数源) | bar 存原始价;adj_factor 变动点→ex_cum_factor,`history_bars` 按查询日重基;持仓过除权日按因子比值合成 split,分红置空 | `test_r1_*`;阶段B 报告 19 项核对 | 总回报口径 = 自研 hfq;不单独建模现金分红/红利税 |
| R2 | 涨停不可买、跌停不可卖 | limit_up/limit_down 由品种规则表算入 bar(主板/ST/科创/创业/北交所含生效日,四舍五入 0.01);RQAlpha `price_limit` 拒单 | `test_r2_*` | 上市首日(科创/创业板前五日)按"无涨跌停"近似 |
| R3 | 停牌口径书面声明 | Tushare daily 停牌无行 ⇒ 停牌 := 交易日 ∧ [该股首个 bar, 数据末日] ∧ 无行;RQAlpha `is_trading_validator` 拒单 | `test_r3_*` | 数据缺口会被当作停牌(保守) |
| R4 | ST 过滤 | namechange 名称 `^S?\*?ST` 区间 → `is_st_stock`;策略层 `filter_st` 剔除 | `test_r4_*`;`test_st_filter_switches_pick_and_rebalances` | ST 涨跌停 5%(主板)同时进 R2 |
| R5 | 退市股在历史池 + 退市清算 | stock_basic 含退市(list_status D)全部入 instruments;退市前末交易日结算按末价折现(`cash_return_by_stock_delisted`) | `test_r5_*` | 无股份转换(吸收合并)数据,按末价折现处理 |
| R6 | T+1 | `market_tplus` 来自品种规则表;当日买入 `closable` 为 0 | `test_r6_*` | 债ETF 等 T+0 品种另挂规则 |
| R7 | 全成本 | `RuleTableStockCostDecider`:佣金/最低佣金/印花税(卖出,按生效日)/过户费(双边,按生效日)全查表 | `test_r7_*` | 集合竞价撮合不加滑点;流动性冲击留给策略研究按品种配置 |

变更纪律:改动任一条目属协议级变更(SOP 横向制度 B)→ 书面提案 + 人类裁决;数值(幅度/费率/生效日)改动走 config 修订记账。
