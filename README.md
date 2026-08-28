# quant_platform

A 股多品种量化研究流水线:想法登记 → 数据 → 因子检验(防挖矿协议)→ 策略包 → 回测(RQAlpha + 本地数据,A 股真实性红线)
→ 目标持仓信号文件 → 只读研发面板。**到信号为止,不下单。** 框架 v1(tag `v1.0.0`,2026-08-28)。

- 新人从这里开始:[`docs/使用指南.md`](docs/使用指南.md)
- 流程宪法 `SOP.md`;架构宪法 `docs/平台蓝图_v2.md`;建设看板 `docs/task_cards/README.md`;时间线 `CHANGELOG.md`
- 一条命令自检:`python -m tools.tracer`(玩具策略全流程,约 9 分钟)
- 面板:`streamlit run dashboard/app.py`

自带的玩具策略(沪深300 低波 20 只月调)只用于验证管道,不构成任何投资建议。
