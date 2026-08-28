# CHANGELOG

## 2026-08-28 策略1 深跌反弹:平台第一个真想法 → 按批前声明证伪(待人类裁决)

- **人类裁决(2026-08-28):废弃。** ideas.md 改"废弃(证伪:…)";策略包 status=retired(新增状态,必须写 retired_reason)永久留档;
  `run_signal` 对 retired 策略拒绝出信号(测试锁死)。

- **S0**:用户想法登记为可证伪假设(research/ideas.md);任务卡第一节把口径逐条声明为默认解释(成交额=20 日均额、历史高=2010 起
  后复权、买 ≤ 高×25% / 卖 ≥ 高×50%、新仓各 10% 已持仓不动、次日收盘成交 + 2% 滑点、千五全包、基准沪深300+中证1000)并写死
  证伪条件——**回测前定,回测后未改**。
- **平台补机制**(资产无关):core.calendar `biweekly_first`;`instruments.BoardUniverse`(板块全市场 PIT,含退市);ctx 增
  `panel(name, asof)`(≤asof 面板)与 `holdings()`(回测=引擎持仓,出信号=上一份信号文件);RQAlpha 胶水提为通用
  `strategies/rq_runner`,执行模式 `next_open`(集合竞价,无滑点)/ `next_close`(次日收盘,滑点生效),策略包级 `execution`/`costs`;
  `run_strategy --set/--tag` 参数覆盖对照实验;`run_sensitivity` 参数平原九宫格(相邻格悬崖判定,`protocol.plateau_cliff_ratio` 0.5,
  `--rebuild` 免重跑)。测试 236→251 全绿。
- **结果**(2019-01-01 → 2025-12-30,本金 10 万,`reports/2026-08-28_回测_dd_rebound/strategy1_report.md`):全成本 总收益 −3.7% /
  年化 −0.56% / 回撤 −51.2% / 夏普 0.09;沪深300 年化 6.89%,中证1000 亦为正;零成本零滑点对照仅 0.92%(成本拖累 1.5pp/年,
  **亏损主因是逻辑本身**);36 次往返胜率 52.8%、中位持有 76 天;持有过 4 只后来退市(含乐视退);2022–2023 连跌未跟上 2024–2025 反弹。
  九宫格(回撤阈 70/75/80% × 反弹阈 40/50/60%)年化全在 −0.72%~+1.99%,无一格接近基准;相邻格相对差大属近零噪声。
- **裁决**:三条证伪条件中"年化 ≤ 沪深300"成立 → **想法证伪**;ideas.md 状态改"已证伪,待人类裁决";策略包 status=research 留档
  (永不删除),**不出信号**。下一步由人类决定:废弃,或改假设新登记(不在旧结果上调参)。
- 施工记录:首版悬崖判定把"只差一个参数"当相邻(0.70 与 0.80 隔格也比),改为网格相邻;报告脚本 `%` 转义。

## 2026-08-28 项目整理:旧项目归档删除,工作区只剩 quant_platform

- 用户裁决:cb_quant(旧可转债)、cb_quant_handover(+zip)、选股策略(mtrading)、根目录 xtquant 时代的 AGENTS.md/docs 全部删除;
  cb_quant 先打最终归档 `D:\qmt_strategy_archive\cb_quant_final_2026-08-28.zip`(25.5M,含 .git/预注册/报告/论文登记,排除
  venv/cache/开源库克隆;台账 ledger 从未落 positions.csv,无实盘记录),xtquant 参考随归档保存;选股策略用户确认无需归档。
- quant_platform 瘦身:删探针环境 research/engine_probe(RQAlpha 已零 bundle)、`~/.rqalpha/bundle` 3.4G、cache 回补日志;
  `cache/fetch_failures.csv` 与 `reports/*_runs/` 保留。合计释放约 7.4G。工作区:`D:\qmt_strategy\{quant_platform, 改造方案}`。
- 新增 `docs/使用指南.md`(傻瓜式:安装 → 数据 → 想法 → 因子 → 策略包 → 回测 → 信号 → 面板 → 示踪弹 → 日常运营)。
- 新增通用回测入口 `python -m backtest.run_strategy --strategy <id>`(任意策略包 → RQAlpha 全成本 → `reports/{日期}_回测_<id>/`;
  玩具策略实测与卡3 全成本版完全一致:年化 4.29% / 回撤 −31.0% / 3453 笔),README.md 入口页。测试 235→236 全绿。

## 2026-08-28 卡7 · 示踪弹贯通 → **框架 v1 完工(tag v1.0.0)**,待人类验收

- **里程碑达成:`python -m tools.tracer --date 2026-08-28` 一条命令把玩具策略从 S0 到面板跑通,6/6 环节通过,545 秒**,
  示踪报告 `reports/2026-08-28_示踪弹/trace.md`:
  S0 想法登记(research/ideas.md 新增 toy_lowvol 可证伪假设行)→ S1 数据体检(退市/PIT/脏值通过,覆盖率项按卡1 人类核验接受)
  → S2 因子检验(**阳性对照第二次运行复现基线 IC_is −0.0398 = 基线**,阴性对照 rejected,已终审因子沿用不再算样本外)
  → S3/S4 回测 + 交叉验证(Δ年化 −0.22pp 通过,相关 0.9994)→ S5 信号(orders_2026-08-26.csv 20 只,落后 0 日)→ 面板 AppTest 四屏无异常。
- `tools/tracer.py`:纯编排 run_stages(失败不中断、逐环节记录)+ 各环节判据只引用各卡既有入口(S1 覆盖率假阳性、
  S5 数据不新鲜拒绝 = 正确行为,均明示);测试用假 runner 不跑长任务。`data.quality` 加 `--date`。
- **示踪弹暴露并修复一个留档漏洞**:同日重跑 `run_factor_tests` 会覆盖首批 factor_verdict.md(样本外只评估一次的证据);
  已恢复原件并改为 `factor_verdict_rerun{N}.md` 不覆盖(测试锁死)。阶段C 目录里重复的自研 CSV 清理。
- **框架 v1 完工判据(蓝图第八节)达成:八卡全部完成,示踪弹贯通;打 tag `v1.0.0`。** 玩具策略永久保留为回归样例
  (合成 store 上 tests/test_toy_lowvol_rq.py、test_signals.py、test_cn_stock_redlines.py、test_factor_pipeline.py 锁死)。
- 测试 234→235 全绿。卡7 之后(蓝图):项目本地 skill(/收尾、/新任务卡)、第一个真策略的 S0 立项——由人类决定。

## 2026-08-28 卡6 · 研发面板(Streamlit,只读 reports)

- **人类验收:2026-08-28 放行(用户"继续"),开卡7 示踪弹。**

- **里程碑达成:浏览器里看到卡3~5 的产出**。`streamlit run dashboard/app.py` 四屏:回测浏览器(净值对比 `*_navs.csv`
  归一化曲线 + 回撤 + 指标表;RQAlpha 报表 summary / 净值 vs 基准 / 期末持仓 / 成交明细)、因子 tear sheet(裁决总表解析自
  factor_verdict.md + 完整报告 + tear sheet 图与 IC/分组 CSV)、信号(orders_*.csv + signal_log.md)、报告(所有 md)。
- **只读**(原则7):解析逻辑全部在纯 python `dashboard/catalog.py`(扫描 `reports/{日期}_{主题}/`:`*_runs/` RQAlpha 报表、
  `*_navs.csv`、`factor_verdict.md`+`tear_<id>_runs/`、`信号_<策略>/orders_*.csv`)与 `dashboard/loaders.py`(utf-8-sig CSV、
  summary.xlsx 两列表、md 表格解析、回撤);app.py 只渲染。测试断言扫描/加载/四屏切换后文件集合不变。
- 无头冒烟:`streamlit.testing.v1.AppTest` 在合成 reports 树(测试)与真实 reports(`reports/2026-08-28_卡6面板/smoke.md`)
  上四屏无异常;真实扫描到回测 run 3、净值文件 1、因子批次 1(3 份 tear sheet)、信号集 1、md 报告 8。
- 净值指标口径抽成 `backtest/metrics.py::nav_stats`(run_toy_backtest / run_rqalpha_toy / 面板共用)。
- 依赖新增 streamlit 1.62.0;测试 220→230 全绿。局限:图表用 Streamlit 内置 line_chart(无交互标注);AppTest 不计数图表/图片
  元素,图形效果需人类目视验收;面板不做任何计算,数据只能是 reports 里已落盘的产出。

## 2026-08-28 卡5 · 策略与信号(两原型基类 + 策略包 + orders CSV 契约)

- **人类验收:2026-08-28 放行(用户"继续"),开卡6 研发面板。**

- **里程碑达成:玩具策略出合规信号文件** `reports/2026-08-28_信号_toy_lowvol/orders_2026-08-26.csv`(20 只等权 5%,
  数据末日 2026-08-26,落后 0 日)+ `signal_log.md`;入口 `python -m signals.run_signal --strategy toy_lowvol`。
- **两原型基类** `strategies/base.py`:Strategy(`signal(asof, ctx)` 纯逻辑、`rebalance_days` 只走 core.calendar)、
  CrossSectionalStrategy(截面选券)、TimeSeriesStrategy(时序配置,测试替身验证契约)。ctx 接口
  constituents/is_st/closes 两个实现 `strategies/context.py`:StoreContext(出信号)/ RQAlphaContext(回测)。
- **策略包格式**(原则5/6)`strategies/package.py`:config 必填 id/name/type/universe/params/benchmark(≥1)/risk/
  crash_definition(≥1);status toy|research|approved,approved 须 approved_by(人类签字);`build_strategy` 从包目录
  加载 strategy.py。第一个包 `strategies/toy_lowvol/`(config.yaml + strategy.py + 说明书.md 含崩溃定义三条,status=toy,
  未签字);旧模块 `strategies/toy_lowvol.py` 升级为包(select_low_vol/low_vol_weights 原路径可用)。
- **风控参数** `strategies/risk.py::apply_risk`(max_weight 封顶留现金、max_positions 截断;等权并列保持策略顺序——
  首版按 symbol 重排曾让对齐版年化 4.86%→4.83%,修正后恢复,交叉验证数字与卡3 完全一致)。
- **信号文件契约** `signals/schema.py`:列 strategy_id/signal_date/symbol/side/target_weight/ref_price/data_asof/
  data_lag_days/generated_at;文件 = 完整目标组合(未列出即 0),side=long,权重 ∈[0,1] 合计 ≤1,ref_price=信号日原始收盘;
  `validate_orders` 拒绝不合规。
- **新鲜度红线**(SOP S5 军规9):`data_lag_days` = 数据末日之后至 asof 的交易日数 > 红线(策略包覆盖 > 平台
  data.freshness_max_lag_days)→ FreshnessError,不落文件;测试用延伸日历的合成 store 验证拒绝与放宽两条路径。
- **回测与出信号同一逻辑**:`strategies/toy_lowvol_rq.make_strategy` 改为用策略包 + RQAlphaContext(旧 params 入口兼容),
  卡3 的 RQAlpha 玩具策略测试与真实数据交叉验证(Δ年化 −0.22pp,相关 0.9994)原样通过;StoreContext 历史 asof 选券
  与回测同日选券一致(测试锁死)。
- 测试 194→220 全绿。局限:交易日历文件只到数据末日,"今日前最近交易日"退化为数据末日时新鲜度可能低估;信号文件只表达
  目标权重,不含持仓差分;时序原型本卡无真实实例。

## 2026-08-28 卡4 · 因子平台(注册表 + 防挖矿管线 + alphalens/quantstats)

- **人类验收:2026-08-28 放行(用户"继续"),开卡5 策略与信号。**

- **里程碑达成:真实数据出完整 tear sheet**(vol_20 / mom_120_20 / rev_20 各一份,alphalens 全套图 + IC/分组 CSV),
  报告 `reports/2026-08-28_卡4因子检验/factor_verdict.md`;入口 `python -m factors.run_factor_tests`(约 8 分钟)。
- **注册表** `factors/registry.yaml` + `factors/registry.py`:五要素必填(id/formula/direction/hypothesis/category),
  状态机 candidate→tested→active|tested_weak|rejected(永不删除),role=candidate/positive_control/negative_control;
  管线只能写回裁决类字段(status/direction/test_report/data_version/oos_evaluated/redundant_with/control_reference),
  公式等定义字段程序不可改;写回保留文件头注释。
- **防挖矿协议平移为可测试机制**(`factors/pipeline.py` + `verdict.py`,阈值全在 config.protocol):批前声明先写进报告再算数
  (阈值/切分/候选数);样本内外切分(2011~2020 / 2021~2026-06);IC/ICIR/t 检验/5 分组单调/top 组换手;BH 校正;
  **样本外每因子只评估一次**(oos_evaluated 非空即跳过并沿用终审);阳性对照(rev_20 反转)首批建基线、其后须复现到容差内,
  阴性对照(种子随机因子)判 active 即本批作废且不写回;to_be_tested 方向由样本内 IC 判定并写回、hypothesis 追加判定日期;
  冗余标注(与 active 因子秩相关 > redundancy_corr_max)。active 不设上限(SOP v2)。
- **T+1 锁死**:`factors/forward_returns.py`(open[T+1+H]/open[T+1]−1)是前瞻收益唯一入口;`factors/alphalens_wrapper.py`
  在入口把价格面板换成 open.shift(−1) 再交 alphalens,裸调用视为违规;`backtest/quantstats_report.py` 净值→html。
- **首批裁决(沪深300 PIT,月频信号 × 20 日持有,样本内 120 截面)**:vol_20 IC_is −0.044 / ICIR −0.20 / 单调 0.70 /
  IC_oos −0.079 → tested_weak(有信号,ICIR 与单调性未达标;方向判为 lower_better);mom_120_20 IC_is 0.014 → rejected;
  rev_20(阳性)IC_is −0.040 方向正确、基线建立,样本外 IC 0.006 → tested_weak;random_control IC_is 0.003 → rejected(阴性通过)。
  结论只对大盘股 universe 有效,不含研究观点。
- 施工记录:首轮试跑 tear sheet 因 alphalens 要求因子日期与交易日历同频而失败(月频信号日不满足),改为喂全日频 PIT 面板
  (正式裁决仍以月频非重叠统计为准);注册表恢复至检验前状态后正式重跑,数字与试跑完全一致,无任何调参。
- 阈值治理记账:config.protocol 新增 signal_freq monthly_first / holding_days 20 / n_quantiles 5 / in_sample
  [2011-01-01,2020-12-31] / out_of_sample [2021-01-01,2026-06-30] / min_periods_ratio 0.6 / negative_control_seed 20260828 /
  alphalens_periods [1,5,20]。依赖新增 alphalens-reloaded 0.4.6、quantstats 0.0.81。测试 152→194 全绿。

## 2026-08-28 卡3 阶段C · 红线验收 + 玩具策略 RQAlpha 版 + 交叉验证(卡3 收尾)

- **人类验收:2026-08-28 放行(用户"继续"),开卡4 因子平台。**

- **卡3 三条放行判据全部满足**:RQAlpha 在 store 数据上跑通玩具策略并出净值/报告;数据源与红线均有合成 store 测试(不触网、
  无 bundle);与自研净值交叉验证通过且差异有解释。里程碑"玩具组合出净值与成交明细"可运行:`python -m backtest.run_rqalpha_toy`。
- **A股股票红线清单落地**(蓝图第七节机制):`instruments/cn_stock_redlines.md` R1-R7 ↔ `tests/test_cn_stock_redlines.py`
  **7/7 通过**——前复权正确 / 涨停不可买·跌停不可卖 / 停牌拒单(口径书面声明)/ ST 过滤 / 退市股在历史池+退市按末价折现 /
  T+1 / 全成本。合成 store 加了涨停·跌停日、退市样本、ST 成分。
- **成本模型**:`backtest/rqalpha_adapter/costs.py` RuleTableStockCostDecider,佣金/最低佣金/印花税(卖出,按生效日)/过户费
  (双边,按生效日)全查品种规则表,替换 RQAlpha 默认万8/0.05%;mod config `costs` 可覆盖个别键(对齐口径用)。
- **玩具策略 RQAlpha 版** `strategies/toy_lowvol_rq.py`:与自研共用 `select_low_vol`、同一 universe、同一调仓日历;
  信号=调仓日收盘 history_bars,执行=次日 `open_auction` 按开盘价先卖后买(`plan_rebalance` 纯函数,整手,预期回款滚动)。
  RQAlpha 事实:日频只有收盘撮合,T+1 开盘只能走集合竞价且不加滑点;`order_value/order_target_percent` 下单时按当时现金截断。
- **交叉验证(SOP S4)** 2011-06→2022-06 沪深300 低波20 月频:自研 年化 5.08% / 回撤 −30.0% vs RQAlpha 对齐版
  4.86% / −30.0%,**Δ年化 −0.22 pp ≤ 容差 1.5**,日收益相关 0.9994,跟踪误差 0.61%,133 个调仓日选券完全一致;
  残差=整手取整、涨跌停拒单、退市处理差异。报告 `reports/2026-08-28_卡3阶段C/toy_lowvol_cross_validation.md`。
- **交叉验证抓到自研引擎 bug 并修复**:停牌日无收盘的持仓按 0 估值、次日回弹,致日收益失真(首轮相关仅 0.55)。
  `backtest/engine.py` 改为沿用末次有效价(TDD)。**卡2 报告中自研 4.41%/−34.4% 作废**,以本报告为准。
- 全成本版(规则表成本 + ST 过滤):年化 4.29% / 回撤 −31.0% / 夏普 0.35 vs 基准 3.82% / −46.7%;成本影响 −0.57 pp/年。
- 修 RQAlpha 报表陷阱:`get_risk_free_rate` 把利率 0 当缺失 → sharpe/alpha NaN,ConstantYieldCurve 0→1e-12。
- **阈值治理记账**:config 新增 `instruments.cn_stock.costs`(commission_rate 0.0002 / min_commission 5 /
  stamp_tax_sell [2008-09-19 0.001, 2023-08-28 0.0005] / transfer_fee [2015-08-01 0.00002, 2022-04-29 0.00001])。
- 测试 136→152 全绿。局限:集合竞价不加滑点;科创板 200 股起/步长 1 未进策略下单层;上市首日涨跌停近似;ETF 未接入。

## 2026-08-27 卡3 阶段B · RQAlpha 数据源铺开(全部数据来自 store,不读 bundle)

- **结论:RQAlpha 6.3.0 跑在我们的 store 上,零 bundle 依赖**(`data_bundle_path` 指向不存在目录照跑)。
  生产代码落在 `backtest/rqalpha_adapter/`(取代 research/engine_probe 的 spike):
  `symbols.py`(.SH/.SZ/.BJ ↔ .XSHG/.XSHE/.BJSE 全流程唯一换算点)、`stores.py`(七个 store:日历←core.calendar 文件模式、
  instruments←stock_basic 含退市+index_daily 指数、日线 bar←stock_daily/index_daily 原始价、复权←adj_factor、
  停牌←缺行推导、ST←namechange)、`data_source.py`(StoreDataSource:继承 BaseDataSource 复用查询逻辑但不调其 __init__)、
  `mod.py`(start_up 注入)。
- **复权口径(重点对账项,防重复复权)**:bar 存原始价;adj_factor 变动点 → ex_cum_factor(history_bars 前/后复权),
  变动日比值 → 合成 split(持仓过除权日按比例调股数/成本,市值连续);**分红置空**(已在因子里)。总回报口径 = 自研 hfq。
  覆盖 `get_ex_cum_factor`:基类按上市日过滤并强插 1.0,我们的因子基准非 1,不覆盖则 2010 前上市股票复权全错。
- **品种规则表落地**(蓝图原则3):`instruments/cn_stock.py` + config `instruments.cn_stock`,涨跌停幅/板块/整手/T+1 全查表,
  代码零数字。停牌口径书面声明:交易日 ∧ [首个bar, 数据末日] ∧ 无行(Tushare daily 停牌无行,全表 volume=0 行数为 0)。
- **真实数据核对 19/19 通过**:`reports/2026-08-27_卡3阶段B/phase_b_store_datasource_check.md`——
  5889 只 CS(含 339 退市)、日历 4043 日、history_bars pre/post 与自研 qfq/hfq 差 0.00、2014-06-04 成交 11.33 = store 收盘、
  除权日 10000→12169 股且市值连续、基准净值 = index_daily 累计收益、沪深300 历史全成分 800 只预载 15.5s。
- **测试 92→136 全绿**(+44:symbols/规则表/stores/datasource/端到端 run_func,合成 store,无 bundle 无网)。
- 环境:rqalpha 6.3.0 装入主 .venv(其在 py3.11 要求 numpy<2:2.4.6→1.26.4,全套测试无破坏);requirements 记账。
  `store.read_table` 加 pyarrow 下推过滤(单标的 6s→1.3s,多标的一次读取)+ `store.date_range`(行组统计,不读数据)。
- **阈值治理记账(新增 config 小节)**:`instruments.cn_stock`(round_lot 100 / market_tplus 1 / price_limit default 0.10、st 0.05 /
  boards KSH {0.20, 2019-07-22, round_lot 200}、GEM {0.20, 2020-08-24}、BJS {0.30, 2020-07-27})、`backtest.risk_free_rate 0.0`。
- 阶段C 待办:红线逐条核对(涨跌停/停牌/退市清算 `cash_return_by_stock_delisted`/T+1/全成本含 RQAlpha 要求显式配置的
  `capital_gain_tax_rate`)、玩具策略 RQAlpha 版、与自研净值交叉验证(SOP S4);上市首日涨跌停特例、ETF 接入列为局限。

## 2026-08-27 卡3 阶段A · Spike 成功(RQAlpha 跑通我们的 store 数据)

- 数据地基全完成:stock_daily 1430万行 + adj_factor 1496万行,均 2010→2026-08-26。
- 卡3 spike 证伪化解:3个小文件让 RQAlpha 引擎读我们的 stock_daily(register_day_bar_store 替换 +
  mod 注入数据源)。铁证:RQAlpha 以 15.93 买入 000001 = 我们 store 当日收盘。接入成本远低于
  "21~31方法"最坏估计。阶段B 待补:ex_factor/日历/instruments/停牌/ST/成分也换我们的。

## 2026-08-27 卡2 裁决:RQAlpha 引擎 + 我们的 store 数据

- 人类裁决(平台方原建议自研):**卡3 引擎走 RQAlpha,但喂我们校验过的 store 数据**
  (写自定义 AbstractDataSource / bundle 转换),不放弃数据主权与单一真相源。
- 后果:卡3 = RQAlpha 接我们 store 的适配层 + 红线核对(用 RQAlpha 内置规则但数据是我们的);
  RQAlpha 的 ricequant bundle 仅作离线参照,不作生产数据源。

## 2026-08-27 卡2 · 引擎调研(报告完成,待人类裁决)

- 全量回补(除 adj_factor 收尾外)完成:stock_daily 1430万行 2010→2026 零失败(修复后的引擎
  经真实全量验证);adj_factor 补到 2022-09(断网暂停,可续)。
- 自研侧收官件:backtest/run_toy_backtest.py(universe+复权价+低波策略+引擎串联)。
  真实数据实测(2011-2022 沪深300低波20月频):策略年化4.41%/回撤-34.4%/夏普0.29 vs
  基准3.82%/-46.7%/0.28,符合低波经典特征,证明自研引擎产出可信。
- RQAlpha 6.3.0 探针评测:装于独立 venv(pandas2.3.3兼容),官方bundle 3.3G下载即用,
  buy_and_hold端到端跑通(约30指标报告)。核心发现:RQAlpha死绑其bundle格式,喂我们的store
  需转格式(会漂移)或写21~31方法数据源;符号.XSHG口径不同。
- 对比报告 reports/2026-08-27_引擎调研/engine_comparison.md;**建议自研轻量**(数据主权+可审计
  优先,RQAlpha留作卡3交叉验证参照)。→ 待人类裁决。

## 2026-08-26 数据源:官方 Tushare token 接入(代理弃用)

- 咸鱼代理(jiaoch.site)证实不可靠:新代理 token 首调成功后约 20~30 次即全接口"接口用法错误"
  (每日配额耗尽,冷却无效)。**弃用代理。**
- 人类购买官方 Tushare 积分,token 接入 config.yaml,base_url 改 `http://api.tushare.pro`。
  实测:daily 5546 行/日、adj_factor 5564 行/日全部正常;编排层主源回归 tushare;
  **退市体检 passed=True(339 只退市股)**——幸存者偏差防线通过,数据地基立住。
- rate_sleep_sec 0.2→0.35(≈170次/分钟,稳在官方 200/min 档下)。
- ETF(fund_daily)/指数(index_daily)口径不敏感,继续走 AKShare 免费省 Tushare 配额。

## 2026-08-26 卡1 · 数据层(代码完成,全量回补阻塞于 Tushare token 续期)

- 交付六件:`data/schema.py`(表注册表 TableSpec + 统一类型校验)、`data/store.py`
  (分片`_parts/{source}__{chunk}`→合并表,来源优先级去重、断点续传、原子写)、
  `data/fetchers/`(base 接口 + tushare HTTP 客户端 + akshare 备源,两源均带重试)、
  `data/fetch.py`(编排:失败记 fetch_failures.csv + 来源熔断切换 + CLI)、
  `data/quality.py`(体检四项 + md/csv 报告)、`data/DATA_DICTIONARY.md`(8 表字段单位表)。
- 首批 8 表:trade_cal / stock_basic(含退市)/ stock_daily(不复权原始存储)/ adj_factor /
  namechange / index_daily / index_weight / fund_daily。指数与 ETF 清单在 config 维护不写死。
- **69 个测试全绿**(不触网,来源注入替身;分片/合并/去重/断点续传/失败记账/来源切换/体检四项全覆盖)。
- **真实网络验证 + 双源设计经受实战**:Tushare 代理端点迁到 `/api`;**Tushare token 已过期**
  → 被正确识别为 SourceUnavailable → 编排层自动切 AKShare → 实拉 trade_cal 8797 行、
  stock_basic 5550 行、浦发日线 3996 行、国债ETF 3263 行;交易日历导出后 core.calendar 切 file 模式;
  体检报告产出(退市样本项正确报警:无 Tushare 则 0 退市股,幸存者偏差防线生效)。
- 发现并修复:AKShare 源缺瞬断重试(其端点会间歇断连),TDD 补测后加 `_call` 重试包装。
- ⛔ **阻塞**:退市股/adj_factor/namechange/index_weight 四类口径敏感表 AKShare 无法替代,
  全量回补与示踪弹(卡7)需人类续 Tushare token 后方可跑真实数据。基础设施已就绪、可断点续传。

## 2026-08-26 卡0 · 仓库奠基(2026-08-24 放行开工,08-26 收尾)

- 蓝图v2 + SOP v2 经人类放行后开工。git init(main分支),宪法入驻:SOP.md /
  CLAUDE.md / docs/平台蓝图_v2.md(蓝图与SOP正本在 D:\qmt_strategy\改造方案\,
  仓库内为施工用副本,状态标记"已放行")。
- core四件:
  - bootstrap:Windows编码+日志统一入口(旧项目GBK样板×12之债的唯一落点)
  - config:yaml加载+点路径覆盖+get辅助+example结构同步校验(structure_diff)
  - calendar:交易日历唯一权威(文件模式/周内近似兜底双源,rebalance_dates通用
    调仓日历——旧项目重复实现×2之债的合并落点;兜底模式带source标记,不可用于出信号)
  - outputs:报告路径服务,{日期}_{主题}归档 + run产出统一*_runs/后缀(旧项目
    报告路径硬编码×6之债的根治)
- tools/check_secrets.py 自 cb_quant 平移(staged扫描 + --scan-dir目录扫描双模式,
  规则原样:禁config类文件名 + 41位以上连续hex拦截),pre-commit钩子已装。
- .gitignore 简化结构:reports/ 的md默认入git,run产出目录统一 *_runs/ 一条规则
  排除(旧项目.gitignore三层白名单之债的根治)。
- config.example.yaml 建立:protocol小节集中全部协议阈值默认值(阈值治理:
  代码只写机制,数值全部config化)。
- 里程碑(卡0验收):`tools/smoke_pipeline.py` 空管道跑通——config加载、example结构
  同步、日历可查(当前周内近似兜底,已标注)、outputs落盘;记录在
  reports/2026-08-26_卡0奠基/smoke.md。19个测试全绿(config/calendar/outputs/check_secrets)。
- GitHub私有仓:本机无 gh CLI,建仓待人类二选一(装gh授权 / 网页建私有仓给URL)。
