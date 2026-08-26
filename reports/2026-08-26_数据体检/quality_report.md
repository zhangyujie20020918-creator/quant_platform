# 数据体检报告

生成时间:2026-08-26T14:04:00
阈值口径(config.quality,批前声明):{'min_delisted_count': 100, 'max_snapshot_gap_days': 45, 'max_dirty_ratio': 0.001, 'min_daily_coverage': 0.95}

## ① 退市样本在否(防幸存者偏差) — 未通过 ❌
- delisted_count: 0
- delisted_with_history: 0
- threshold: 100

## ② PIT 时点正确性 — 通过 ✅
- daily_after_calendar: 0
- latest_open_day: 2026-12-31
- max_snapshot_gap: 0
- gap_threshold: 45

## ③ 脏值扫描 — 通过 ✅
- rows: 0
- dirty_rows: 0
- dirty_ratio: 0.0
- threshold: 0.001
- reasons: {}

## ④ 逐日覆盖曲线 — 通过 ✅
- low_coverage_days: 0
- min_coverage: None
- threshold: 0.95

