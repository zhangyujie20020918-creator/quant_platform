# coding: utf-8
import pandas as pd
import pytest

from data.schema import FIRST_BATCH, SchemaError, TableSpec, get_spec, validate

FIRST_BATCH_EXPECTED = {"trade_cal", "stock_basic", "stock_daily", "adj_factor",
                        "namechange", "index_daily", "index_weight", "fund_daily"}


def test_first_batch_tables_registered_with_consistent_specs():
    assert set(FIRST_BATCH) == FIRST_BATCH_EXPECTED
    for name in FIRST_BATCH:
        spec = get_spec(name)
        assert isinstance(spec, TableSpec) and spec.name == name
        assert set(spec.key) <= set(spec.columns), name
        assert spec.date_col is None or spec.date_col in spec.columns, name
        assert spec.description


def test_get_spec_unknown_table_raises_with_hint():
    with pytest.raises(KeyError) as e:
        get_spec("nope")
    assert "stock_daily" in str(e.value)


def _spec():
    return TableSpec(name="t", description="test",
                     columns={"date": "date", "symbol": "str", "close": "float", "vol": "int"},
                     key=("date", "symbol"), date_col="date")


def test_validate_orders_columns_and_coerces_types():
    df = pd.DataFrame({"vol": ["100", "200"], "close": ["1.5", "2.5"],
                       "symbol": ["600000.SH", "000001.SZ"], "date": ["20260102", "2026-01-02"],
                       "extra": [1, 2]})
    out = validate(df, _spec())
    assert list(out.columns) == ["date", "symbol", "close", "vol"]      # 额外列丢弃,按spec排序
    assert str(out["date"].dtype).startswith("datetime64")
    assert out["date"].tolist() == [pd.Timestamp("2026-01-02")] * 2
    assert out["close"].dtype == float and out["vol"].dtype.kind == "i"
    assert out["symbol"].tolist() == ["000001.SZ", "600000.SH"]         # 按主键排序


def test_validate_keeps_source_column_for_provenance():
    df = pd.DataFrame({"date": ["2026-01-02"], "symbol": ["600000.SH"], "close": [1.0],
                       "vol": [1], "source": ["tushare"]})
    out = validate(df, _spec())
    assert list(out.columns) == ["date", "symbol", "close", "vol", "source"]


def test_validate_rejects_missing_column():
    df = pd.DataFrame({"date": ["2026-01-02"], "symbol": ["600000.SH"], "close": [1.0]})
    with pytest.raises(SchemaError, match="vol"):
        validate(df, _spec())


def test_validate_rejects_duplicate_keys():
    df = pd.DataFrame({"date": ["2026-01-02"] * 2, "symbol": ["600000.SH"] * 2,
                       "close": [1.0, 1.0], "vol": [1, 1]})
    with pytest.raises(SchemaError, match="主键重复"):
        validate(df, _spec())


def test_validate_rejects_unparseable_date_and_non_numeric():
    bad_date = pd.DataFrame({"date": ["not-a-date"], "symbol": ["600000.SH"], "close": [1.0], "vol": [1]})
    with pytest.raises(SchemaError, match="date"):
        validate(bad_date, _spec())
    bad_num = pd.DataFrame({"date": ["2026-01-02"], "symbol": ["600000.SH"], "close": ["abc"], "vol": [1]})
    with pytest.raises(SchemaError, match="close"):
        validate(bad_num, _spec())


def test_validate_allows_missing_values_in_non_key_columns():
    df = pd.DataFrame({"date": ["2026-01-02"], "symbol": ["600000.SH"], "close": [None], "vol": [None]})
    out = validate(df, _spec())
    assert pd.isna(out["close"].iloc[0]) and pd.isna(out["vol"].iloc[0])


def test_validate_rejects_missing_key_values():
    df = pd.DataFrame({"date": [None], "symbol": ["600000.SH"], "close": [1.0], "vol": [1]})
    with pytest.raises(SchemaError, match="主键缺失"):
        validate(df, _spec())
