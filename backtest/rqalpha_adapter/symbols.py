# coding: utf-8
"""symbol(平台口径 600000.SH)↔ RQAlpha order_book_id(600000.XSHG)的唯一换算点。

全流程只在这里换算:进 RQAlpha 前 to_order_book_id,出 RQAlpha 后 to_symbol;
其他模块禁止各自拼后缀(旧项目符号体系分散之债)。未知后缀报错,不猜。
"""
_SYMBOL_TO_RQ = {"SH": "XSHG", "SZ": "XSHE", "BJ": "BJSE"}
_RQ_TO_SYMBOL = {v: k for k, v in _SYMBOL_TO_RQ.items()}


def _split(code, table, what):
    body, sep, suffix = code.partition(".")
    if not sep or suffix not in table:
        raise ValueError("无法识别的%s后缀: %r(已知: %s)" % (what, code, ", ".join(sorted(table))))
    return body, table[suffix]


def to_order_book_id(symbol):
    """'600000.SH' → '600000.XSHG';'000001.SZ' → '000001.XSHE';'832317.BJ' → '832317.BJSE'。"""
    body, suffix = _split(symbol, _SYMBOL_TO_RQ, "symbol")
    return body + "." + suffix


def to_symbol(order_book_id):
    """'600000.XSHG' → '600000.SH'(to_order_book_id 的逆)。"""
    body, suffix = _split(order_book_id, _RQ_TO_SYMBOL, "order_book_id")
    return body + "." + suffix
