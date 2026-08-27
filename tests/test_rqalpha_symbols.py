# coding: utf-8
"""symbol(600000.SH)↔ RQAlpha order_book_id(600000.XSHG)双向映射:全流程唯一换算点。"""
import pytest

from backtest.rqalpha_adapter.symbols import to_order_book_id, to_symbol


@pytest.mark.parametrize("symbol, obid", [
    ("600000.SH", "600000.XSHG"),
    ("000001.SZ", "000001.XSHE"),
    ("832317.BJ", "832317.BJSE"),
    ("000300.SH", "000300.XSHG"),      # 指数同样映射到 XSHG
])
def test_round_trip(symbol, obid):
    assert to_order_book_id(symbol) == obid
    assert to_symbol(obid) == symbol


def test_unknown_suffix_rejected_rather_than_guessed():
    with pytest.raises(ValueError):
        to_order_book_id("600000.XX")
    with pytest.raises(ValueError):
        to_symbol("600000.XXXX")
    with pytest.raises(ValueError):
        to_order_book_id("600000")
