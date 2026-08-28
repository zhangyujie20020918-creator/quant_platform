# coding: utf-8
"""Streamlit 面板无头冒烟(streamlit.testing AppTest):四屏切换无异常,只读。"""
import os

import pytest

from core.config import ROOT
from tests.test_dashboard_catalog import tree  # noqa: F401  复用合成 reports 树

APP = os.path.join(ROOT, "dashboard", "app.py")


@pytest.fixture
def app(tree, monkeypatch):   # noqa: F811
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("QUANT_PLATFORM_REPORTS", tree)
    at = AppTest.from_file(APP, default_timeout=120)
    return at


def test_all_screens_render_without_exception(app, tree):   # noqa: F811
    at = app.run()
    assert not at.exception
    radio = at.sidebar.radio[0]
    assert radio.options == ["回测浏览器", "因子 tear sheet", "信号", "报告"]
    for screen in radio.options:
        at = at.sidebar.radio[0].set_value(screen).run()          # 每次从最新树取元素,旧元素会指向失效的 session key
        assert not at.exception, screen
        assert any(screen in h.value for h in list(at.header) + list(at.subheader) + list(at.title)), screen


def test_dashboard_never_writes(app, tree):   # noqa: F811
    from tests.test_dashboard_catalog import _snapshot
    before = _snapshot(tree)
    at = app.run()
    for screen in at.sidebar.radio[0].options:
        at.sidebar.radio[0].set_value(screen).run()
    assert _snapshot(tree) == before
