# coding: utf-8
import pandas as pd
import pytest

from data.fetchers.base import Source, SourceUnavailable
from data.fetchers.tushare import TushareError, TushareHTTP, TushareSource


# ---------- HTTP 客户端(注入假 session,不触网) ----------

class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http %d" % self.status_code)


class _Session:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _ok(fields, items):
    return _Resp({"code": 0, "msg": "", "data": {"fields": fields, "items": items}})


def test_query_posts_official_protocol_and_parses_items():
    s = _Session([_ok(["ts_code", "close"], [["600000.SH", 10.5]])])
    http = TushareHTTP("tok", "http://proxy", session=s, rate_sleep=0, timeout=7)
    df = http.query("daily", fields="ts_code,close", trade_date="20260105")
    assert s.calls[0]["url"] == "http://proxy" and s.calls[0]["timeout"] == 7
    assert s.calls[0]["json"] == {"api_name": "daily", "token": "tok",
                                  "params": {"trade_date": "20260105"}, "fields": "ts_code,close"}
    assert df.to_dict("records") == [{"ts_code": "600000.SH", "close": 10.5}]


def test_query_retries_network_errors_then_succeeds():
    s = _Session([ConnectionError("boom"), _Resp({}, status=502), _ok(["a"], [[1]])])
    http = TushareHTTP("tok", "http://proxy", session=s, rate_sleep=0, max_retries=3, backoff=0)
    assert http.query("x").iloc[0, 0] == 1 and len(s.calls) == 3


def test_query_gives_up_after_max_retries():
    s = _Session([ConnectionError("boom")] * 2)
    http = TushareHTTP("tok", "http://proxy", session=s, rate_sleep=0, max_retries=2, backoff=0)
    with pytest.raises(ConnectionError):
        http.query("x")


def test_query_waits_on_rate_limit_message(monkeypatch):
    slept = []
    monkeypatch.setattr("data.fetchers.tushare.time.sleep", lambda s: slept.append(s))
    s = _Session([_Resp({"code": 40203, "msg": "抱歉,您每分钟最多访问该接口50次"}), _ok(["a"], [[1]])])
    http = TushareHTTP("tok", "http://proxy", session=s, rate_sleep=0, backoff=0, rate_limit_sleep=20)
    assert http.query("x").iloc[0, 0] == 1
    assert 20 in slept


def test_query_raises_unavailable_on_token_error_without_retry():
    s = _Session([_Resp({"code": 2002, "msg": "token无效"})] * 3)
    http = TushareHTTP("tok", "http://proxy", session=s, rate_sleep=0, backoff=0)
    with pytest.raises(SourceUnavailable):
        http.query("x")
    assert len(s.calls) == 1


def test_query_raises_tushare_error_on_other_api_errors():
    s = _Session([_Resp({"code": 40001, "msg": "参数错误"})])
    http = TushareHTTP("tok", "http://proxy", session=s, rate_sleep=0, backoff=0)
    with pytest.raises(TushareError, match="参数错误"):
        http.query("x")


# ---------- 来源:分片规划 + 字段映射(注入假 http) ----------

class _FakeHTTP:
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def query(self, api_name, fields=None, **params):
        self.calls.append((api_name, params))
        return self.handler(api_name, params)


CFG = {"calendar": {"file": "nope.csv", "exchange": "SSE"},
       "data": {"symbols": {"index": ["000300.SH", "000001.SH"], "index_weight": ["000300.SH"],
                            "etf": ["511010.SH"]}}}


def test_source_interface_and_supports():
    src = TushareSource(CFG, http=_FakeHTTP(lambda a, p: pd.DataFrame()))
    assert isinstance(src, Source) and src.name == "tushare"
    for t in ["trade_cal", "stock_basic", "stock_daily", "adj_factor", "namechange",
              "index_daily", "index_weight", "fund_daily"]:
        assert src.supports(t), t
    assert not src.supports("nope")


def test_plan_chunks_per_table(tmp_path):
    src = TushareSource(CFG, http=_FakeHTTP(lambda a, p: pd.DataFrame()), root=str(tmp_path))
    assert src.plan("trade_cal", "2010-01-01", "2026-12-31") == ["20100101_20261231"]
    assert src.plan("stock_basic", "2010-01-01", "2026-12-31") == ["L", "D", "P"]
    assert src.plan("stock_daily", "2026-01-05", "2026-01-07") == ["20260105", "20260106", "20260107"]
    assert src.plan("adj_factor", "2026-01-09", "2026-01-12") == ["20260109", "20260112"]   # 跳过周末
    assert src.plan("namechange", "2010-01-01", "2026-12-31") == ["all"]
    assert src.plan("index_daily", "2010-01-01", "2026-12-31") == ["000300.SH", "000001.SH"]
    assert src.plan("index_weight", "2024-06-01", "2026-03-01") == ["000300.SH_2024", "000300.SH_2025", "000300.SH_2026"]
    assert src.plan("fund_daily", "2025-01-01", "2026-03-01") == ["511010.SH_2025", "511010.SH_2026"]


def test_fetch_stock_daily_maps_fields_and_units():
    raw = pd.DataFrame({"ts_code": ["600000.SH"], "trade_date": ["20260105"], "open": [10.0], "high": [11.0],
                        "low": [9.0], "close": [10.5], "pre_close": [10.0], "vol": [1234.0], "amount": [5678.0]})
    http = _FakeHTTP(lambda a, p: raw)
    src = TushareSource(CFG, http=http)
    df = src.fetch("stock_daily", "20260105")
    assert http.calls[0][0] == "daily" and http.calls[0][1]["trade_date"] == "20260105"
    row = df.iloc[0]
    assert row["symbol"] == "600000.SH" and row["date"] == "20260105"
    assert row["volume"] == 1234.0 * 100 and row["amount"] == 5678.0 * 1000     # 手→股,千元→元
    assert set(df.columns) >= {"date", "symbol", "open", "high", "low", "close", "pre_close", "volume", "amount"}


def test_fetch_trade_cal_and_stock_basic_and_adj_factor():
    def handler(api, p):
        if api == "trade_cal":
            assert p["exchange"] == "SSE" and p["start_date"] == "20100101" and p["end_date"] == "20261231"
            return pd.DataFrame({"exchange": ["SSE"], "cal_date": ["20260105"], "is_open": [1]})
        if api == "stock_basic":
            assert p["list_status"] == "D"
            return pd.DataFrame({"ts_code": ["600001.SH"], "name": ["邯郸钢铁"], "exchange": ["SSE"], "market": ["主板"],
                                 "list_status": ["D"], "list_date": ["19980122"], "delist_date": ["20100114"]})
        if api == "adj_factor":
            return pd.DataFrame({"ts_code": ["600000.SH"], "trade_date": ["20260105"], "adj_factor": [12.3]})
        raise AssertionError(api)
    src = TushareSource(CFG, http=_FakeHTTP(handler))
    cal = src.fetch("trade_cal", "20100101_20261231")
    assert cal.iloc[0].to_dict() == {"date": "20260105", "exchange": "SSE", "is_open": 1}
    basic = src.fetch("stock_basic", "D")
    assert basic.iloc[0]["symbol"] == "600001.SH" and basic.iloc[0]["delist_date"] == "20100114"
    adj = src.fetch("adj_factor", "20260105")
    assert adj.iloc[0]["adj_factor"] == 12.3


def test_fetch_namechange_paginates_until_short_page():
    pages = [pd.DataFrame({"ts_code": ["600000.SH"] * 3, "name": ["a", "b", "c"],
                           "start_date": ["20100101", "20150101", "20200101"],
                           "end_date": ["20141231", "20191231", None], "change_reason": ["x"] * 3}),
             pd.DataFrame({"ts_code": ["000001.SZ"], "name": ["d"], "start_date": ["20100101"],
                           "end_date": [None], "change_reason": ["y"]})]
    http = _FakeHTTP(lambda a, p: pages[p["offset"] // 3])
    src = TushareSource(CFG, http=http, page_limit=3)
    df = src.fetch("namechange", "all")
    assert len(df) == 4 and [c[1]["offset"] for c in http.calls] == [0, 3]


def test_fetch_index_weight_fund_daily_index_daily():
    def handler(api, p):
        if api == "index_weight":
            # 按月分片(规避单次行数上限):只有覆盖到该快照日的那一月返回数据,其余月为空
            assert p["index_code"] == "000300.SH"
            if p["start_date"] == "20250101":
                return pd.DataFrame({"index_code": ["000300.SH"], "con_code": ["600000.SH"],
                                     "trade_date": ["20250131"], "weight": [1.5]})
            return pd.DataFrame()
        if api == "fund_daily":
            assert p == {"ts_code": "511010.SH", "start_date": "20260101", "end_date": "20261231"}
            return pd.DataFrame({"ts_code": ["511010.SH"], "trade_date": ["20260105"], "open": [1.0], "high": [1.0],
                                 "low": [1.0], "close": [1.0], "pre_close": [1.0], "vol": [10.0], "amount": [20.0]})
        if api == "index_daily":
            assert p["ts_code"] == "000300.SH"
            return pd.DataFrame({"ts_code": ["000300.SH"], "trade_date": ["20260105"], "open": [1.0], "high": [1.0],
                                 "low": [1.0], "close": [1.0], "vol": [10.0], "amount": [20.0]})
        raise AssertionError(api)
    src = TushareSource(CFG, http=_FakeHTTP(handler))
    w = src.fetch("index_weight", "000300.SH_2025")
    assert w.iloc[0].to_dict() == {"date": "20250131", "index_symbol": "000300.SH", "symbol": "600000.SH", "weight": 1.5}
    f = src.fetch("fund_daily", "511010.SH_2026")
    assert f.iloc[0]["volume"] == 1000.0 and f.iloc[0]["amount"] == 20000.0
    i = src.fetch("index_daily", "000300.SH")
    assert i.iloc[0]["volume"] == 1000.0 and "pre_close" not in i.columns


def test_fetch_empty_response_returns_empty_frame_with_columns():
    src = TushareSource(CFG, http=_FakeHTTP(lambda a, p: pd.DataFrame()))
    df = src.fetch("stock_daily", "20260103")
    assert df.empty and "close" in df.columns
