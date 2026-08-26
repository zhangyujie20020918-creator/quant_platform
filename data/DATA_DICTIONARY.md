# 数据字段单位表(DATA_DICTIONARY)

平台统一口径的唯一权威(旧项目"单位/格式约定分散无中央文档"之债的根治)。
S1 例行维护:每新增一张表/一列,先在此登记再落库。

## 全局约定

- **date 类列**:统一 `datetime64`(schema 校验时从 "YYYYMMDD"/ISO 字符串强制转换)。
- **symbol**:`600000.SH` / `000001.SZ` / `000300.SH` 形式(交易所后缀大写);各来源的原生代码由适配器映射到此。
- **volume**:股(Tushare 原生=手,适配器 ×100;AKShare 原生=手,×100)。
- **amount**:元(Tushare 原生=千元,×1000;AKShare 原生=元,不变)。
- **source**:每张合并表带此溯源列,值为来源名(tushare/akshare);主键冲突时按 `data.source_priority` 取胜者。
- 缺失值:非主键列允许 NaN/None;主键列不允许缺失或重复(schema 校验拦截)。

## 各表(首批)

| 表 | 列 | 类型 | 单位/口径 | 备注 |
|---|---|---|---|---|
| trade_cal | date, exchange, is_open | date/str/bool | — | 主键(date,exchange);导出 trading_days.csv 只取 is_open=1 |
| stock_basic | symbol, name, exchange, market, list_status, list_date, delist_date | str×5+date×2 | list_status∈{L上市,D退市,P暂停} | 主键 symbol;**含退市股**(防幸存者偏差) |
| stock_daily | date, symbol, open, high, low, close, pre_close, volume, amount | date/str/float×7 | 价=元(**不复权,原始存储**),volume=股,amount=元 | 主键(date,symbol);复权在读端用 adj_factor 做 |
| adj_factor | date, symbol, adj_factor | date/str/float | 复权因子(后复权基准) | 仅主源;各源基准不同不可混用 |
| namechange | symbol, name, start_date, end_date, change_reason | str×3+date×2 | — | 主键(symbol,start_date);ST/*ST 状态由 name 前缀判定 |
| index_daily | date, symbol, open, high, low, close, volume, amount | date/str/float×6 | 同 stock_daily(无 pre_close) | 主键(date,symbol) |
| index_weight | date, index_symbol, symbol, weight | date/str×2/float | weight=百分数(如 1.5 表示1.5%) | 主键(date,index_symbol,symbol);月度快照,PIT 取最近≤t 的一份 |
| fund_daily | date, symbol, open, high, low, close, pre_close, volume, amount | date/str/float×7 | 同 stock_daily | 主键(date,symbol);ETF 场内行情 |

## 已知局限(迁移/使用方须知)

- AKShare 备源的 stock_basic 只给在市股(list_status 一律 L),退市/暂停状态以 Tushare 主源为准。
- AKShare 备源不接 adj_factor / namechange / index_weight(口径敏感,见 fetchers/akshare.py 头注)。
- pre_close:AKShare 路径由 close 前移一日推算,主源 Tushare 直接给;跨来源拼接时以主源为准。
