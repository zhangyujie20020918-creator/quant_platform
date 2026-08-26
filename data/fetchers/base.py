# coding: utf-8
"""来源接口(原则2"来源不写死"的落点)。

一个来源 = 三件事:supports(表) / plan(表,起,止)→分片键列表 / fetch(表,分片键)→统一schema的DataFrame。
**分片策略属于来源**(按日批量还是按标的,由来源自己决定),编排层只管"逐片拉、存在即跳过"。
is_open_chunk:分片是否"未封口"(区间含今天/整表刷新型),未封口的分片每次都重拉,封口的存在即跳过。
"""


class SourceUnavailable(Exception):
    """来源整体不可用(鉴权失败/连不上):编排层应放弃该来源,切换下一优先级。"""


class Source:
    name = ""

    def supports(self, table):
        raise NotImplementedError

    def plan(self, table, start, end):
        raise NotImplementedError

    def fetch(self, table, chunk):
        raise NotImplementedError

    def is_open_chunk(self, table, chunk):
        return False
