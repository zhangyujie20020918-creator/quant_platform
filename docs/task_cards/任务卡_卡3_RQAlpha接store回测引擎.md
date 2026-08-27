# 任务卡 · 卡3 回测引擎(RQAlpha 接我们的 store)

开工:待定 | 前置:卡2 裁决(RQAlpha 引擎 + 我们 store 数据)| 蓝图:第七节红线 + 第八节卡3

## 一、定义(做什么)

让 RQAlpha 6.3.0 的回测引擎跑在**我们校验过的 store 数据**上(不用 ricequant bundle),
即写一个 RQAlpha 自定义数据源把 cache 喂进去,并核对 A股红线,最终用 RQAlpha 跑通玩具策略。

**数据主权不放弃**:store 仍是唯一真相源;RQAlpha 只是消费它的回测引擎。
ricequant 的 3.3G bundle 仅留探针环境作离线参照,不进生产。

## 二、技术路径(spike 先行,证伪再铺开)

### 阶段A · Spike(先证明路走得通,再投入)
- 写**最小自定义数据源**:只服务单只股票的日线 bar(从 store.stock_daily 读),
  接 RQAlpha 的 `AbstractDataSource` 必需方法子集。
- 目标:RQAlpha `run buy_and_hold` 在**我们的一只股票数据**上跑通,产出 portfolio.csv。
- **若此步成本已过高/接口过深 → 回到人类,重议是否改 bundle 转换或退回自研**(诚实止损)。

### 阶段B · 铺开数据源(spike 通过后)
RQAlpha 数据源需要喂的东西 ← 我们 store 的对应表:
| RQAlpha 需要 | 我们的来源 | 备注 |
|---|---|---|
| instruments(证券列表/上市退市) | stock_basic | 含退市,防幸存者偏差 |
| trading_calendar | trade_cal / core.calendar | 已有 |
| 日线 bar(history_bars/get_bar) | stock_daily | 原始价 |
| 复权(dividend/split 或 adjusted) | adj_factor | RQAlpha 内部复权 vs 我们预复权,口径要对齐 |
| 停牌(is_suspended) | stock_daily 缺行 / volume=0 | 需推导 |
| ST(is_st_stock) | namechange | 名称含 ST/*ST |
| 指数成分(index_components) | index_weight | 沪深300 PIT |
| 符号转换 .SH↔.XSHG | 新建映射层 | 全流程双向 |

### 阶段C · 红线核对 + 玩具策略
- 用 RQAlpha 内置规则(涨跌停/停牌/T+1)但数据是我们的,核对蓝图第七节红线清单。
- 把玩具策略(沪深300低波20月频)写成 RQAlpha handle_bar/scheduler 形态,跑 2011-2022。
- **交叉验证(SOP S4)**:与自研侧净值(年化4.41%/回撤-34.4%)对比,差异在容差内即互证;
  差异大则定位口径分歧(复权/成本/执行时点)。

## 三、判据(放行条件)
- RQAlpha 在我们 store 数据上跑通玩具策略,产出净值+报告;
- 自定义数据源有测试(注入合成 store,不触网);
- 与自研侧净值交叉验证,差异有解释;
- 红线清单逐条核对结论。

## 四、验收(人类看什么)
1. RQAlpha 跑我们数据的玩具策略净值 vs 自研净值对比;
2. 数据源适配层代码 + 测试;
3. 红线核对表 + 口径差异说明。

## 五、风险与未知(诚实标注)
- `AbstractDataSource` 21~31 方法,实际必需子集要 spike 才知道,可能比预想深。
- RQAlpha 内部复权口径 vs 我们 adj_factor 预复权,可能重复复权或口径错位——重点对账项。
- 符号体系(.XSHG)、交易所枚举、instrument 类型映射是琐碎但易错的量。
- **数据依赖**:adj_factor 需补完 2022→2026(断网暂停中);spike 与 2011-2022 铺开不阻塞,
  全区间回测需回补收尾。

## 施工记录

### 阶段A · Spike 成功(2026-08-27)
**结论:RQAlpha 接我们 store 的路径证伪化解成功,接入成本远低于对比报告最坏估计。**
- 只用 3 个小文件(research/engine_probe/ 下,gitignore):store_datasource.py(StoreDayBarStore
  读 stock_daily→RQAlpha bar 结构数组 + StoreDataSource 子类化 BaseDataSource 复用 bundle 管道、
  仅 register_day_bar_store 替换 CS 日线)、store_mod.py(start_up 里 env.set_data_source)、
  run_spike.py(buy_and_hold on 000001)。
- **铁证**:RQAlpha 2011-01-05 以 15.93 买入 000001,= 我们 store 的 000001.SZ 当日收盘 15.93,
  证明引擎读的是我们的价格。245 交易日跑通,期末 96.88 万(平安2011跌~3%,合理)。
- 关键机制:BaseDataSource 是可插拔 store 架构(register_day_bar_store/instruments/dividend/split/
  ex_factor);main.py 先跑 mod.start_up 再 `if not hasattr(env,'data_source')`,故 mod 设源即覆盖默认。
- **spike 局限(阶段B待补)**:仍用 bundle 的 ex_factor(复权)/日历/instruments/停牌/ST/成分;
  阶段B 要把这些也换成我们的(adj_factor→ex_factor_store,stock_basic→instruments 含退市,
  trade_cal→calendar,namechange→ST,index_weight→成分),并解决 .SH↔.XSHG 全流程映射。
- **裁决止损点未触发**:接口深度可控,继续阶段B。

### 阶段B · 数据源铺开完成(2026-08-27)
**结论:RQAlpha 全部数据来自我们的 store,不再读任何 bundle 文件(`data_bundle_path` 指向不存在目录照跑)。**
- 生产代码 `backtest/rqalpha_adapter/`(取代 spike):`symbols.py`(符号唯一换算点,含 .BJ↔.BJSE)、`stores.py`
  (七个 store,对应本卡第二节表格逐项落地)、`data_source.py`(StoreDataSource:继承 BaseDataSource 复用 history_bars/
  instruments 查询逻辑,但不调其 __init__——那里硬编码打开 14 个 bundle 文件)、`mod.py`(start_up 注入,mod config 可传
  root/config_path/preload)。品种规则表 `instruments/cn_stock.py` + config `instruments.cn_stock`:涨跌停幅(主板/ST/
  科创/创业/北交所含生效日)、整手(科创 200)、T+1 全查表,代码零数字。
- **复权对账(本卡头号风险项)**:bar 存原始价;adj_factor 变动点 → ex_cum_factor(前/后复权看历史),变动日比值 →
  合成 split(持仓过除权日),分红置空。实测 history_bars pre/post 与自研 `backtest.prices` qfq/hfq 差 0.00;
  端到端 2014-06-12 除权:10000 股 → 12169 股,市值比 1.00306 ≈ 9.71/9.68。覆盖 `get_ex_cum_factor`(基类强插 1.0 陷阱)。
- 停牌口径:交易日 ∧ [首个 bar, 数据末日] ∧ 无行(实测 000001 2014-07-15 真实停牌 → True)。ST:namechange 名称
  `^S?\*?ST` 区间(实测 000005 2021-05-06 起 True)。日历:core.calendar 文件模式,拒绝周内近似。
- 真实数据核对 19/19 通过:`reports/2026-08-27_卡3阶段B/phase_b_store_datasource_check.md`;运行器
  `python -m backtest.run_rqalpha_check`。沪深300 历史全成分 800 只预载 15.5s(store.read_table 加 pyarrow 下推过滤)。
- 测试 92→136 全绿(合成 store `tests/rq_seed.py`,无 bundle 无网)。环境:rqalpha 6.3.0 入主 .venv(numpy 降 1.26.4)。
- **阶段C 待办**:红线逐条核对(涨跌停/停牌/退市清算/T+1/全成本——RQAlpha 提示 `base.capital_gain_tax_rate` 需显式配置)、
  玩具策略 RQAlpha 版、与自研净值交叉验证。局限:上市首日涨跌停以 NaN(无限制)近似;ETF/基金未接入 instruments。

### 阶段C · 红线验收 + 玩具策略 RQAlpha 版 + 交叉验证(2026-08-28,卡3 收尾,待人类验收)
**结论:三条放行判据全部满足——RQAlpha 在 store 数据上跑通玩具策略并出净值/报告;数据源与红线均有合成 store 测试;
与自研净值交叉验证通过且差异有解释。**
- **红线清单落地**(蓝图第七节):`instruments/cn_stock_redlines.md`(A股股票品种包,R1-R7 条目↔测试映射),验收测试
  `tests/test_cn_stock_redlines.py` 一次合成回测按日期触发七个场景,**7/7 通过**:前复权 / 涨停不可买·跌停不可卖 / 停牌拒单 /
  ST 过滤 / 退市股在池+退市按末价折现 / T+1 / 全成本。
- **成本模型**:`backtest/rqalpha_adapter/costs.py` RuleTableStockCostDecider——佣金/最低佣金/印花税(卖出,按生效日)/
  过户费(双边,按生效日)全部来自品种规则表 config `instruments.cn_stock.costs`,替换 RQAlpha 默认万8/0.05%;mod 里注册,
  mod config `costs` 可覆盖个别键(交叉验证对齐口径用)。
- **玩具策略 RQAlpha 版** `strategies/toy_lowvol_rq.py`:与自研共用 `select_low_vol`(从 toy_lowvol 提出的唯一选券函数)、
  同一 universe(instruments.universe PIT)、同一调仓日历(core.calendar);信号=调仓日收盘 history_bars,执行=次日
  `open_auction` 按开盘价先清非目标→减仓→依剩余现金整手买入(`plan_rebalance` 纯函数有测试)。RQAlpha 日频只有收盘撮合,
  T+1 开盘只能走集合竞价且不加滑点;`order_value/order_target_percent` 下单时按当时现金截断,故用 `order_shares` 自算数量。
- **交叉验证(SOP S4)** 2011-06→2022-06 沪深300 低波20 月频,报告 `reports/2026-08-28_卡3阶段C/toy_lowvol_cross_validation.md`:
  自研 年化 5.08%/回撤 −30.0% vs RQAlpha 对齐版 4.86%/−30.0%,**Δ年化 −0.22 pp(容差 1.5)通过**,日收益相关 0.9994,
  跟踪误差 0.61%,133 个调仓日选券完全一致。残差来源:整手取整、涨跌停拒单、退市折现(RQAlpha)vs 无价按 0(自研)。
- **交叉验证抓到自研引擎一个 bug**:停牌日无收盘的持仓按 0 估值(次日"暴涨"回来),导致卡2 报告的自研净值
  日收益失真(相关 0.55、回撤 −34.4%)。已按 TDD 修复(`backtest/engine.py` 沿用末次有效价),**卡2 报告里自研的
  4.41%/−34.4% 作废,以本报告 5.08%/−30.0%(无滑点口径)为准**。
- **全成本版**(规则表成本 + ST 过滤 + 内置红线):年化 4.29% / 回撤 −31.0% / 夏普 0.35,基准 3.82% / −46.7%;
  成本影响 −0.57 pp/年。RQAlpha 报表目录 `rq_full_runs/`。
- 修一处 RQAlpha 报表陷阱:`get_risk_free_rate` 把利率 0 当缺失 → sharpe/alpha NaN;ConstantYieldCurve 0→1e-12。
- 测试 136→152 全绿。局限:集合竞价不加滑点;科创板 200 股起/步长 1 的整手规则未进策略下单层;上市首日涨跌停近似。
