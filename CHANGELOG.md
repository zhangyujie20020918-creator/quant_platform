# CHANGELOG

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
