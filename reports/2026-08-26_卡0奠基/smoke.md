# 卡0 空管道冒烟记录

运行时间:2026-08-26T12:52:19

- config 加载 OK:protocol.ic_min=0.03,data.backfill_start=2010-01-01
- config.yaml 与 config.example.yaml 结构一致 OK
- 日历可查 OK:source=weekday_approx,今天是否交易日=True,下一交易日=2026-08-27,今年剩余月度调仓日=5个
-   (注意:当前为周内近似模式,不含节假日;卡1落盘真实日历后自动切换)
- outputs 落盘 OK:2026-08-26_卡0奠基 / smoke_runs
