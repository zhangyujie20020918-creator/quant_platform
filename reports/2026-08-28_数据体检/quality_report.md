# 数据体检报告

生成时间:2026-08-28T16:58:21
阈值口径(config.quality,批前声明):{'min_delisted_count': 100, 'max_snapshot_gap_days': 45, 'max_dirty_ratio': 0.001, 'min_daily_coverage': 0.95}

## ① 退市样本在否(防幸存者偏差) — 通过 ✅
- delisted_count: 339
- delisted_with_history: 271
- threshold: 100

## ② PIT 时点正确性 — 通过 ✅
- daily_after_calendar: 0
- latest_open_day: 2026-08-26
- max_snapshot_gap: 36
- gap_threshold: 45

## ③ 脏值扫描 — 通过 ✅
- rows: 14305899
- dirty_rows: 0
- dirty_ratio: 0.0
- threshold: 0.001
- reasons: {}

## ④ 逐日覆盖曲线 — 未通过 ❌
- low_coverage_days: 1152
- min_coverage: 0.49011147069399497
- threshold: 0.95

覆盖曲线明细:coverage_curve.csv
