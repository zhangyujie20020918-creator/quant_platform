# coding: utf-8
"""统一进程初始化:编码与日志。所有入口脚本第一行调用 init()。

旧项目之债的落点:`sys.stdout.reconfigure(encoding="utf-8")` 样板曾在12个脚本里
各复制一份,漏写一次导致858秒计算成果在最后一步打印时崩掉(Windows GBK控制台)。
本模块是这段逻辑的唯一住所,入口脚本不得自行处理编码。
"""
import logging
import sys


def init(name="quant_platform", level=logging.INFO):
    """进程初始化:Windows控制台UTF-8 + 根日志配置。幂等,可重复调用。返回命名logger。"""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(name)
