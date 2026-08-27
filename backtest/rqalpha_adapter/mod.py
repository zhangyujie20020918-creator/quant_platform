# coding: utf-8
"""RQAlpha mod:在 start_up 里把引擎数据源换成 StoreDataSource。

RQAlpha main.py 先跑各 mod 的 start_up,之后 `if not hasattr(env, "data_source")` 才装默认
bundle 源——所以本 mod 设了源,bundle 就不会被碰。用法(run_func / run_file 的 config):
    "mod": {"store": {"enabled": True, "lib": "backtest.rqalpha_adapter.mod",
                      "root": <仓库根,可省>, "config_path": <config.yaml,可省>,
                      "preload": ["000001.SZ", ...]  # 可省:批量预载的平台 symbol}}
"""
from rqalpha.interface import AbstractMod


class StoreMod(AbstractMod):
    def start_up(self, env, mod_config):
        from backtest.rqalpha_adapter.data_source import StoreDataSource
        from core.config import ROOT, load_config

        config_path = getattr(mod_config, "config_path", None)
        root = getattr(mod_config, "root", None) or ROOT
        preload = list(getattr(mod_config, "preload", None) or [])
        cfg = load_config(config_path or None)
        env.set_data_source(StoreDataSource(cfg, root=root, preload=preload))

    def tear_down(self, code, exception=None):
        pass


def load_mod():
    return StoreMod()
