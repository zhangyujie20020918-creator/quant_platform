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
(收尾时填)

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
