# 任务卡看板

规则:一卡一会话;收尾 = 测试全绿 + 里程碑可运行 + CHANGELOG;跨卡必经人类验收。
卡序列与验收判据正本见 `docs/平台蓝图_v2.md` 第八节。

| 卡 | 内容 | 里程碑 | 状态 |
|---|---|---|---|
| 卡0 仓库奠基 | git+GitHub私有仓+宪法入驻+core四件+pre-commit | 空管道跑通(config/outputs/日历) | **完成(2026-08-26)**:19测试绿,冒烟见 reports/2026-08-26_卡0奠基/smoke.md;GitHub远程待人类定 |
| 卡1 数据层 | store+schema+双源fetcher+首批表清单+体检四项 | 任一标的取数成功+体检报告 | **完成(2026-08-27)**:8 表 2010→2026-08-26 全量回补(stock_daily 1430 万行);体检退市/PIT/脏值通过,覆盖率项核验为 2015 股灾停牌假阳性,数据已接受 |
| 卡2 引擎调研 | 时间盒1天:自研轻量 vs RQAlpha | 对比报告→人类裁决 | **完成(2026-08-27)**:对比报告建议自研;**人类裁决:RQAlpha 引擎 + 我们的 store 数据**(保数据主权) |
| 卡3 回测引擎 | 按裁决实现+品种规则表+红线验收测试+成本模型 | 玩具组合出净值与成交明细 | **完成,人类验收放行(2026-08-28 用户"继续")**:阶段A spike ✅;阶段B RQAlpha 零 bundle 跑 store(核对 19/19,`reports/2026-08-27_卡3阶段B/`)✅;阶段C 红线 R1-R7 验收测试 7/7 + 品种规则表成本 + 玩具策略 RQAlpha 版,与自研交叉验证 Δ年化 −0.22pp/相关 0.9994(`reports/2026-08-28_卡3阶段C/`)✅;152 测试绿 |
| 卡4 因子平台 | registry+协议平移+alphalens/quantstats接入 | 任一因子出完整tear sheet | **完成,人类验收放行(2026-08-28 用户"继续")**:注册表五要素+状态机、防挖矿管线(T+1 锁死/BH/对照组/样本外只评估一次/批前声明)、alphalens+quantstats 薄封装;首批 4 因子真实数据裁决 `reports/2026-08-28_卡4因子检验/`(vol_20 tested_weak、mom_120_20 rejected、阳性对照基线建立、阴性对照 rejected),3 份 tear sheet;194 测试绿 |
| 卡5 策略与信号 | 两原型基类+策略包格式+orders CSV契约 | 玩具策略出合规信号文件 | **完成,人类验收放行(2026-08-28 用户"继续")**:`strategies/{base,package,risk,context}.py` + 第一个策略包 `strategies/toy_lowvol/`(config/strategy/说明书,status=toy)+ `signals/{schema,run_signal}.py`(新鲜度红线);真实信号 `reports/2026-08-28_信号_toy_lowvol/orders_2026-08-26.csv`(20 只);回测与出信号同一 signal(),卡3 交叉验证数字不变;220 测试绿 |
| 卡6 研发面板 | Streamlit两屏:回测浏览器/因子tear sheet | 面板看到卡3~5产出 | **完成,人类验收放行(2026-08-28 用户"继续")**:`dashboard/{catalog,loaders,app}.py` 四屏(回测浏览器/因子 tear sheet/信号/报告),只读 reports;AppTest 无头冒烟真实 reports 四屏无异常 `reports/2026-08-28_卡6面板/smoke.md`;`streamlit run dashboard/app.py`;230 测试绿 |
| 卡7 示踪弹 | 玩具策略全流程贯通 | 框架v1完工打tag | **完成,待人类验收(2026-08-28)**:`python -m tools.tracer` 一条命令 S0→S1→S2→S3/S4→S5→面板 6/6 通过(545s),`reports/2026-08-28_示踪弹/trace.md`;阳性对照复现基线、阴性对照 rejected、交叉验证 Δ −0.22pp、信号 20 只;tag `v1.0.0`;235 测试绿 |

## 策略任务卡(框架 v1 之后的研究,一想法一卡)

| 卡 | 想法 | 状态 | 结论 / 去向 |
|---|---|---|---|
| 策略1 深跌反弹 `dd_rebound` | 主板+创业板,历史高点回撤 75% 买、反弹到高点一半卖,两周调仓持 10 只 | **废弃(2026-08-28 人类裁决,证伪)** | 全成本年化 −0.56% vs 沪深300 6.89%(零成本亦仅 0.92%);九宫格全在 −0.7%~+2%,相邻格相对差大(近零噪声)。`reports/2026-08-28_回测_dd_rebound/strategy1_report.md` |
