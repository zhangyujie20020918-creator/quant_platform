# quant_platform 项目规则

## 宪法(违反即打回)

- `SOP.md` 是研发流程宪法;`docs/平台蓝图_v2.md` 是架构宪法(八原则:品种即插件 /
  来源不写死 / 品种规则表 / 阈值不写死 / 策略包契约 / 基准可配置 / 产出只经outputs /
  里程碑收尾)。
- **可转债适应项目,不是项目适应可转债**:任何品种特有逻辑只能住在品种包
  (instruments条目 + 该品种红线清单 + fetcher注册),不得进核心层。
- 一切数值阈值住 config(`protocol` 小节),代码与文档只写机制;改阈值 = 批前声明 +
  修订记账(SOP"阈值治理")。
- 所有入口脚本第一行 `from core.bootstrap import init`(Windows GBK 之债的唯一落点);
  产出一律经 `core/outputs`,禁止手写 reports 路径。
- `config.yaml` / `config.snapshot.yaml` 永不入git(pre-commit拦截;新clone先装钩子,
  安装命令见 `tools/check_secrets.py` 文件头)。
- 对话不是记录:重要判断当日落 CHANGELOG 或报告,否则视为未发生。

## 想法与外部来源登记

凡催生过任务卡或策略假设的外部文章,无论载体(论文/研报/博客/帖子),一律按
`research/papers/README.md` 登记;自有想法记 `research/ideas.md`(一行可证伪假设 +
数据可得性预判 + 目标品种),写不出证伪条件的不进S1。

## 施工纪律

一卡一会话;每卡收尾 = 测试全绿 + 里程碑可运行 + CHANGELOG;跨卡必经人类验收。
当前看板:`docs/task_cards/README.md`。

## 回测引擎(卡3 起)

- 引擎 = RQAlpha 6.3.0 + 我们的 store 数据源(`backtest/rqalpha_adapter/`,零 bundle);品种规则表 = config
  `instruments.cn_stock` + `instruments/cn_stock.py`;A股股票红线清单 `instruments/cn_stock_redlines.md` ↔
  验收测试 `tests/test_cn_stock_redlines.py`。新品种 = 新规则表条目 + 新红线清单 + 新测试,核心零修改。
- 策略回测走 `run_func(..., mod.store={enabled, lib:"backtest.rqalpha_adapter.mod", preload:[symbols]})`;
  自研 `backtest/engine.py` 只作交叉验证对照(SOP S4)。

## 因子平台(卡4 起)

- 注册表 `factors/registry.yaml`(五要素必填,状态机,rejected/tested_weak 永不删除)是唯一权威;实现在
  `factors/lib/<id>.py`(`compute(ctx)`);检验只走 `python -m factors.run_factor_tests`(批前声明先于数字,
  样本外每因子只评估一次,对照组失败本批作废,阈值全在 config.protocol)。
- 前瞻收益唯一入口 `factors/forward_returns.py`(open[T+1+H]/open[T+1]−1);alphalens 只能经
  `factors/alphalens_wrapper.py` 调用(价格入口锁 T+1 开盘),裸调用视为违规。

## 策略包与信号(卡5 起)

- 策略 = 策略包 `strategies/<id>/{config.yaml, strategy.py, 说明书.md}`(`strategies/package.py` 校验:五段必填、
  benchmark ≥1、crash_definition ≥1、approved 须人类签字);信号逻辑写在 `Strategy.signal(asof, ctx)`(引擎无关),
  回测(RQAlphaContext)与出信号(StoreContext)共用同一份代码;调仓日只走 core.calendar;风控经 `strategies/risk.py`。
- 出信号只走 `python -m signals.run_signal --strategy <id>`:数据落后超过新鲜度红线即拒绝;文件契约见
  `signals/schema.py`(完整目标组合,未列出即 0)。status≠approved 的策略信号不得用于交易。
