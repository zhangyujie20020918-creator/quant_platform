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
