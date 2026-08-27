# coding: utf-8
"""A股股票交易成本:全部来自品种规则表 instruments.cn_stock.costs,替换 RQAlpha 默认(万8 佣金 / 0.05% 印花税)。

复用 RQAlpha StockTransactionCostDecider 的最低佣金按单结算逻辑,只换费率来源:
- commission_rate / min_commission:佣金(双边)与最低佣金;
- stamp_tax_sell:印花税(卖出单边),按生效日列表逐交易日取值;
- transfer_fee:过户费(双边),按生效日列表,计入 other_fees。
"""
from rqalpha.core.events import EVENT
from rqalpha.interface import TransactionCost
from rqalpha.mod.rqalpha_mod_sys_transaction_cost.deciders import StockTransactionCostDecider

from instruments.cn_stock import dated_rate


class RuleTableStockCostDecider(StockTransactionCostDecider):
    def __init__(self, costs, event_bus):
        super().__init__(commission_multiplier=1, min_commission=float(costs["min_commission"]),
                         tax_multiplier=1, pit_tax=False, event_bus=event_bus)
        self.commission_rate = float(costs["commission_rate"])
        self._stamp = list(costs.get("stamp_tax_sell") or [])
        self._transfer = list(costs.get("transfer_fee") or [])
        self.tax_rate = 0.0
        self._transfer_rate = 0.0
        event_bus.add_listener(EVENT.PRE_BEFORE_TRADING, self._on_trading_day)

    def _on_trading_day(self, event):
        self.tax_rate = dated_rate(self._stamp, event.trading_dt)
        self._transfer_rate = dated_rate(self._transfer, event.trading_dt)

    def calc(self, args):
        base = super().calc(args)
        other = args.price * args.quantity * self._transfer_rate
        return TransactionCost(commission=base.commission, tax=base.tax, other_fees=other)

    def batch_estimate(self, delta_quantities, prices):
        return super().batch_estimate(delta_quantities, prices) + delta_quantities.abs() * prices * self._transfer_rate
