# 示踪弹报告(2026-08-28)· 玩具策略 toy_lowvol 全流程

总判定:**全部通过 → 框架 v1 完工判据达成**(6/6 环节通过,合计 545 秒)

| 环节 | 内容 | 结果 | 耗时 | 产出 |
|---|---|---|---|---|
| S0 | 想法登记 | 通过 | 0s | `research/ideas.md` |
| S1 | 数据体检 | 通过 | 33s | `reports/2026-08-28_数据体检/quality_report.md` |
| S2 | 因子检验(对照组 + 裁决) | 通过 | 329s | `reports/2026-08-28_卡4因子检验/factor_verdict.md`<br>`factors/registry.yaml` |
| S3/S4 | 回测 + 交叉验证 | 通过 | 173s | `reports/2026-08-28_卡3阶段C/toy_lowvol_cross_validation.md` |
| S5 | 信号 | 通过 | 3s | `reports/2026-08-28_信号_toy_lowvol/` |
| 面板 | 面板无头冒烟 | 通过 | 6s | `dashboard/app.py` |

## 各环节末尾输出

### S0 想法登记(退出码 0)

(python 检查)

```
ideas.md 已登记:| 2026-08-24 | 玩具·低波异象:沪深300 成分内近 20 日波动最低的 20 只等权月调,风险调整后收益优于指数(可证伪:样本外 vol_20 
```

### S1 数据体检(退出码 2)

`D:\qmt_strategy\quant_platform\.venv\Scripts\python.exe -m data.quality --date 2026-08-28`

```
仅覆盖率项未通过(卡1 人类核验:2015 股灾千股停牌假阳性,数据已接受)
体检完成:存在未通过项;报告 D:\qmt_strategy\quant_platform\reports\2026-08-28_数据体检
16:57:59 INFO __main__: delisting: 通过
16:58:03 INFO __main__: pit: 通过
16:58:09 INFO __main__: dirty: 通过
16:58:21 INFO __main__: coverage: 未通过
```

### S2 因子检验(对照组 + 裁决)(退出码 0)

`D:\qmt_strategy\quant_platform\.venv\Scripts\python.exe -m factors.run_factor_tests --date 2026-08-28`

```
17:01:27 INFO factor_tests: tear sheet vol_20 → D:\qmt_strategy\quant_platform\reports\2026-08-28_卡4因子检验\tear_vol_20_runs
17:02:26 INFO matplotlib.category: Using categorical units to plot a list of strings that are all parsable as floats or dates. If these strings should be plotted as numbers, cast to the appropriate data type before plotting.
17:02:26 INFO matplotlib.category: Using categorical units to plot a list of strings that are all parsable as floats or dates. If these strings should be plotted as numbers, cast to the appropriate data type before plotting.
D:\qmt_strategy\quant_platform\.venv\Lib\site-packages\alphalens\tears.py:293: UserWarning: FigureCanvasAgg is non-interactive, and thus cannot be shown
  plt.show()
D:\qmt_strategy\quant_platform\.venv\Lib\site-packages\alphalens\tears.py:386: UserWarning: FigureCanvasAgg is non-interactive, and thus cannot be shown
  plt.show()
D:\qmt_strategy\quant_platform\.venv\Lib\site-packages\alphalens\utils.py:928: UserWarning: Skipping return periods that aren't exact multiples of days.
  warnings.warn(
D:\qmt_strategy\quant_platform\.venv\Lib\site-packages\alphalens\tears.py:463: UserWarning: FigureCanvasAgg is non-interactive, and thus cannot be shown
  plt.show()
17:03:50 INFO factor_tests: tear sheet rev_20 → D:\qmt_strategy\quant_platform\reports\2026-08-28_卡4因子检验\tear_rev_20_runs
```

### S3/S4 回测 + 交叉验证(退出码 0)

`D:\qmt_strategy\quant_platform\.venv\Scripts\python.exe -m backtest.run_rqalpha_toy --date 2026-08-28`

```
17:03:58 INFO toy_backtest: 月频调仓日 133 个(2011-06-01 → 2022-06-01)
17:04:39 INFO toy_backtest: 有效调仓日 133/133(每期选 20 只)
17:04:41 INFO toy_backtest: === 自研引擎玩具策略结果(2011-06-01 → 2022-06-30) ===
17:04:41 INFO toy_backtest: 策略: 总收益 69.8% | 年化 5.08% | 最大回撤 -30.0% | 夏普 0.39
17:04:41 INFO toy_backtest: 基准(000300.SH): 年化 3.82% | 最大回撤 -46.7% | 夏普 0.28
17:04:41 INFO toy_backtest: 年化超额 1.26% | 成交笔数 3809 | 产出 D:\qmt_strategy\quant_platform\reports\2026-08-28_卡3阶段C
17:04:41 INFO rqalpha_toy: ② RQAlpha 对齐版...
[2026-08-28 17:04:41.045952] WARN: system_log: The strategy requires explicit configuration of base.capital_gain_tax_rate, which currently has a default value of 0 and will be changed to a non-zero value in a future version.(The configuration description can be found at https://www.ricequant.com/doc/rqalpha-plus/api/config)
17:05:41 INFO rqalpha_toy:    总收益 66.1% | 年化 4.86% | 最大回撤 -30.0% | 夏普 0.39(61s,133 信号,3489 笔)
17:05:41 INFO rqalpha_toy: ③ RQAlpha 全成本版...
17:06:43 INFO rqalpha_toy:    总收益 56.7% | 年化 4.29% | 最大回撤 -31.0% | 夏普 0.35(62s,3453 笔)
17:06:43 INFO rqalpha_toy: ④ 交叉验证:Δ年化 -0.22 pp(容差 1.5)→ 通过;日收益相关 0.9994,跟踪误差 0.61%
```

### S5 信号(退出码 0)

`D:\qmt_strategy\quant_platform\.venv\Scripts\python.exe -m signals.run_signal --strategy toy_lowvol`

```
信号文件已生成
17:06:47 INFO run_signal: 信号文件 D:\qmt_strategy\quant_platform\reports\2026-08-28_信号_toy_lowvol\orders_2026-08-26.csv:20 只,权重合计 1.0000,数据落后 0 日(红线 2),状态 toy
```

### 面板 面板无头冒烟(退出码 0)

(python 检查)

```
AppTest 四屏无异常(只读)
```
