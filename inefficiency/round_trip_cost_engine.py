class RoundTripCostEngine:

    def calculate(
        self,
        buy_price,
        sell_price,
        quantity=1.0,
        buy_brokerage=0.0,
        sell_brokerage=0.0,
        exchange_charges=0.0,
        clearing_charges=0.0,
        buy_tax=0.0,
        sell_tax=0.0,
        gst_or_vat=0.0,
        stamp_duty=0.0,
        fx_spread=0.0,
        slippage=0.0,
        funding_cost=0.0,
        freight=0.0,
        warehouse_cost=0.0,
        handling_cost=0.0,
        hedging_cost=0.0
    ):

        gross_buy_value = buy_price * quantity
        gross_sell_value = sell_price * quantity
        gross_spread = gross_sell_value - gross_buy_value

        total_cost = (
            buy_brokerage
            + sell_brokerage
            + exchange_charges
            + clearing_charges
            + buy_tax
            + sell_tax
            + gst_or_vat
            + stamp_duty
            + fx_spread
            + slippage
            + funding_cost
            + freight
            + warehouse_cost
            + handling_cost
            + hedging_cost
        )

        net_profit = gross_spread - total_cost

        if gross_buy_value == 0:
            net_profit_pct = 0.0
        else:
            net_profit_pct = (net_profit / gross_buy_value) * 100

        return {
            "gross_buy_value": gross_buy_value,
            "gross_sell_value": gross_sell_value,
            "gross_spread": gross_spread,
            "total_round_trip_cost": total_cost,
            "net_profit": net_profit,
            "net_profit_pct": net_profit_pct,
            "is_profitable_after_round_trip": net_profit > 0
        }
