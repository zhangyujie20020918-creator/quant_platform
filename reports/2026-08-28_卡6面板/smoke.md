# 卡6 研发面板 · 无头冒烟(2026-08-28)

`streamlit.testing.v1.AppTest` 在真实 reports/ 上跑 dashboard/app.py 四屏(只读);人类验收请 `streamlit run dashboard/app.py`。

- reports 根:`reports`
- 扫描:回测 run 3(2026-08-28 卡3阶段C / rq_align, 2026-08-28 卡3阶段C / rq_full, 2026-08-27 卡3阶段B / rq_check);净值文件 1;因子批次 1(tear sheet:mom_120_20/rev_20/vol_20);信号集 1;md 报告 9

- 屏「回测浏览器」:无异常,0.7s;渲染 dataframe 4 个、markdown 2 段(图表/图片元素 AppTest 不计数,人类验收目视)
- 屏「因子 tear sheet」:无异常,0.2s;渲染 dataframe 3 个、markdown 3 段(图表/图片元素 AppTest 不计数,人类验收目视)
- 屏「信号」:无异常,0.0s;渲染 dataframe 1 个、markdown 2 段(图表/图片元素 AppTest 不计数,人类验收目视)
- 屏「报告」:无异常,0.1s;渲染 dataframe 0 个、markdown 1 段(图表/图片元素 AppTest 不计数,人类验收目视)

- 总耗时 5.4s;面板代码零写文件调用(dashboard/ 无 open(..., 'w') / to_csv / makedirs)。
