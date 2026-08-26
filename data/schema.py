# coding: utf-8
"""表注册表与统一 schema 校验(数据层唯一口径;任务卡_卡1 第一节)。

统一约定(详见 data/DATA_DICTIONARY.md):
- `date` 类列:datetime64;接受 "YYYYMMDD" / ISO 字符串 / datetime 输入
- `symbol`:"600000.SH" 形式(所有来源的适配器都映射到此)
- volume=股,amount=元(适配器负责从来源单位换算)
- 每张表可带 `source` 溯源列(写入分片时由编排层加,校验时原样保留)
表清单只是注册项,不代表平台预设任何研究方向;新品种/新表 = 新注册项。
"""
from dataclasses import dataclass, field

import pandas as pd


class SchemaError(ValueError):
    pass


@dataclass(frozen=True)
class TableSpec:
    name: str
    description: str
    columns: dict                 # 有序:列名 -> "date" | "str" | "float" | "int" | "bool"
    key: tuple                    # 主键列
    date_col: str = None          # 用于区间读取/增量的日期列;静态表为 None
    sources: tuple = field(default_factory=tuple)   # 来源优先级覆盖;空=用 config data.source_priority


TABLES = {}


def register(spec):
    TABLES[spec.name] = spec
    return spec


def get_spec(name):
    try:
        return TABLES[name]
    except KeyError:
        raise KeyError("未注册的表: %r;已注册: %s" % (name, ", ".join(sorted(TABLES)))) from None


# ---------------------------------------------------------------------------
# 首批表(示踪弹最小需求 + 品种红线所需;清单在任务卡里定,可按需追加)
# ---------------------------------------------------------------------------

register(TableSpec(
    name="trade_cal", description="交易所交易日历(开市日)",
    columns={"date": "date", "exchange": "str", "is_open": "bool"},
    key=("date", "exchange"), date_col="date"))

register(TableSpec(
    name="stock_basic", description="股票基本信息,含退市(D)与暂停上市(P)",
    columns={"symbol": "str", "name": "str", "exchange": "str", "market": "str",
             "list_status": "str", "list_date": "date", "delist_date": "date"},
    key=("symbol",)))

register(TableSpec(
    name="stock_daily", description="股票日线(不复权,原始存储;复权在读端用 adj_factor 做)",
    columns={"date": "date", "symbol": "str", "open": "float", "high": "float", "low": "float",
             "close": "float", "pre_close": "float", "volume": "float", "amount": "float"},
    key=("date", "symbol"), date_col="date"))

register(TableSpec(
    name="adj_factor", description="复权因子(来源基准不同不可混用,仅主源)",
    columns={"date": "date", "symbol": "str", "adj_factor": "float"},
    key=("date", "symbol"), date_col="date"))

register(TableSpec(
    name="namechange", description="证券名称变更历史(ST/*ST 状态的来源)",
    columns={"symbol": "str", "name": "str", "start_date": "date", "end_date": "date",
             "change_reason": "str"},
    key=("symbol", "start_date"), date_col="start_date"))

register(TableSpec(
    name="index_daily", description="指数日线",
    columns={"date": "date", "symbol": "str", "open": "float", "high": "float", "low": "float",
             "close": "float", "volume": "float", "amount": "float"},
    key=("date", "symbol"), date_col="date"))

register(TableSpec(
    name="index_weight", description="指数成分与权重(月度快照,PIT 用最近一次 ≤ t 的快照)",
    columns={"date": "date", "index_symbol": "str", "symbol": "str", "weight": "float"},
    key=("date", "index_symbol", "symbol"), date_col="date"))

register(TableSpec(
    name="fund_daily", description="场内基金(ETF)日线",
    columns={"date": "date", "symbol": "str", "open": "float", "high": "float", "low": "float",
             "close": "float", "pre_close": "float", "volume": "float", "amount": "float"},
    key=("date", "symbol"), date_col="date"))

FIRST_BATCH = tuple(TABLES)


# ---------------------------------------------------------------------------
# 校验与类型统一
# ---------------------------------------------------------------------------

_NA_STRINGS = {"", "none", "nan", "nat", "null"}


def _is_na(series):
    """原始值是否视为缺失(None/NaN/空串/"None"等)。"""
    return series.isna() | series.astype(str).str.strip().str.lower().isin(_NA_STRINGS)


def _to_date(series, col):
    if str(series.dtype).startswith("datetime64"):
        return series.dt.normalize()
    na = _is_na(series)
    text = series.astype(str).str.strip()
    out = pd.to_datetime(text.where(~na), format="%Y%m%d", errors="coerce")
    retry = out.isna() & ~na
    if retry.any():
        out[retry] = pd.to_datetime(text[retry], errors="coerce")
    bad = out.isna() & ~na
    if bad.any():
        raise SchemaError("列 %s 有 %d 个日期无法解析,例如 %r" % (col, int(bad.sum()), text[bad].iloc[0]))
    return out.dt.normalize()


def _to_float(series, col):
    na = _is_na(series)
    out = pd.to_numeric(series.where(~na), errors="coerce")
    bad = out.isna() & ~na
    if bad.any():
        raise SchemaError("列 %s 有 %d 个值不是数值,例如 %r" % (col, int(bad.sum()), series[bad].iloc[0]))
    return out.astype(float)


def _to_int(series, col):
    return _to_float(series, col).astype("Int64")


def _to_str(series, _col):
    na = _is_na(series)
    return series.astype(str).str.strip().where(~na, None).astype(object)


_TRUE, _FALSE = {"1", "true", "t", "yes", "y"}, {"0", "false", "f", "no", "n"}


def _to_bool(series, col):
    na = _is_na(series)
    text = series.astype(str).str.strip().str.lower()
    out = pd.Series(pd.NA, index=series.index, dtype="boolean")
    out[text.isin(_TRUE)] = True
    out[text.isin(_FALSE)] = False
    bad = out.isna() & ~na
    if bad.any():
        raise SchemaError("列 %s 有 %d 个值不是布尔,例如 %r" % (col, int(bad.sum()), series[bad].iloc[0]))
    return out


_COERCE = {"date": _to_date, "float": _to_float, "int": _to_int, "str": _to_str, "bool": _to_bool}


def validate(df, spec):
    """按 spec 校验并统一类型:缺列/主键缺失/主键重复/不可解析 → SchemaError。
    返回按 spec 列序(+可选 source 列)、按主键排序的新 DataFrame;额外列丢弃。"""
    missing = [c for c in spec.columns if c not in df.columns]
    if missing:
        raise SchemaError("表 %s 缺列: %s" % (spec.name, ", ".join(missing)))
    out = pd.DataFrame(index=df.index)
    for col, kind in spec.columns.items():
        out[col] = _COERCE[kind](df[col], col)
    if "source" in df.columns:
        out["source"] = df["source"].astype(str)
    key = list(spec.key)
    if out[key].isna().any().any():
        raise SchemaError("表 %s 主键缺失: %s" % (spec.name, out[key].isna().sum().to_dict()))
    dup = out.duplicated(subset=key)
    if dup.any():
        raise SchemaError("表 %s 主键重复: %d 行(键 %s)" % (spec.name, int(dup.sum()), key))
    return out.sort_values(key).reset_index(drop=True)
