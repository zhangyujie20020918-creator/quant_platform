# 卡4 因子检验报告(2026-08-28)

## 一、批前声明(判据先于数据;写于任何统计计算之前)

- universe:000300.SH 历史成分(PIT,按信号日取最近一次快照)
- 信号日频率 monthly_first;前瞻收益 = open[T+1+20] / open[T+1] − 1(T+1 口径锁死);分组数 5
- 样本内 2011-01-01 ~ 2020-12-31;样本外 2021-01-01 ~ 2026-06-30(**每因子只评估一次,结果即终审**)
- 阈值(config.protocol):ic_min=0.03,icir_min=0.3,monotonicity_min=0.8,oos_retention_min=0.5,bh_alpha=0.05,positive_control_tolerance=0.4,redundancy_corr_max=0.6
- 本批因子 4 个(vol_20, mom_120_20, rev_20, random_control),其中候选 2 个(其余为对照组:阳性 rev_20 / 阴性 random_control)
- active ⇔ 样本内 |IC|≥ic_min ∧ |ICIR|≥icir_min ∧ |单调性|≥monotonicity_min ∧ 样本外同号且保留≥oos_retention_min ∧ BH 显著;有信号但不满足 → tested_weak;无信号 → rejected

## 二、裁决总表

| 因子 | 角色 | IC_is | ICIR_is | n_is | t | p(BH校正) | 单调性 | top组换手 | IC_oos | ICIR_oos | n_oos | 裁决 | 方向 | 冗余 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vol_20 | candidate | -0.0435 | -0.201 | 120 | -2.20 | 0.0445 | 0.70 | 0.55 | -0.0787 | -0.321 | 65 | **tested_weak** | lower_better | — |
| mom_120_20 | candidate | 0.0141 | 0.070 | 120 | 0.77 | 0.4434 | 1.00 | 0.36 | -0.0106 | -0.051 | 65 | **rejected** | higher_better | — |
| rev_20 | positive_control | -0.0398 | -0.205 | 120 | -2.24 | 0.0445 | -1.00 | 0.76 | 0.0064 | 0.033 | 65 | **tested_weak** | lower_better | — |
| random_control | negative_control | 0.0029 | 0.050 | 120 | 0.54 | 0.5871 | 0.00 | 0.81 | 0.0019 | 0.032 | 65 | **rejected** | to_be_tested | — |

## 三、对照组

- rev_20:阳性对照首次运行,基线 IC_is=-0.0398 建立
- random_control:阴性对照判 rejected,正常

## 四、分组平均前瞻收益(样本内,组1=因子最低)

- vol_20:Q1 0.0088 | Q2 0.0068 | Q3 0.0085 | Q4 0.0100 | Q5 0.0101
- mom_120_20:Q1 0.0064 | Q2 0.0075 | Q3 0.0090 | Q4 0.0107 | Q5 0.0113
- rev_20:Q1 0.0133 | Q2 0.0094 | Q3 0.0083 | Q4 0.0079 | Q5 0.0059
- random_control:Q1 0.0095 | Q2 0.0071 | Q3 0.0090 | Q4 0.0091 | Q5 0.0091

## 五、tear sheet(alphalens,T+1 开盘口径)

- vol_20:`reports\2026-08-28_卡4因子检验\tear_vol_20_runs`
- mom_120_20:`reports\2026-08-28_卡4因子检验\tear_mom_120_20_runs`
- rev_20:`reports\2026-08-28_卡4因子检验\tear_rev_20_runs`

## 六、局限声明

- 月频信号 × 20 日持有,样本内约 120 个截面,t 检验功效有限;结论只对该 universe(大盘股)有效。
- 阳性对照首批只能建立基线,不能证明管线正确;第二批起才构成真正的阳性检验。
- 因子面板只用价格(后复权),未做行业/市值中性化;IC 为 Spearman 秩相关。
- 耗时 466 秒。
