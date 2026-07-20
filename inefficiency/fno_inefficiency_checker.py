"""
F&O inefficiency math — pure functions, no I/O.

Two real, quote-computable inefficiencies:

1. Futures basis (spot vs future, "time" inefficiency):
   fair_future = spot * (1 + r * t/365)
   future above fair  -> CASH_AND_CARRY   (buy spot, sell future)
   future below fair  -> REVERSE_CASH_AND_CARRY (short spot, buy future)

2. Put-call parity (options, "instrument" inefficiency):
   a conversion package (buy spot + buy put + sell call, same strike K)
   costs (S + P - C) today and pays exactly K at expiry.
   K above financed cost -> CONVERSION; below -> REVERSAL.

Both are emitted as OpportunityRankingEngine candidates so the existing
cost + settlement + capital + liquidity stack gives the final verdict.
Financing is baked into the fair/cost side, so the candidate's own
financing rate is 0 (no double count). Lock-up = days to expiry.
"""
from ai.live_opportunity_gate import DEFAULT_GATE_CONFIG


def _candidate(symbol, strategy, direction, buy_price, sell_price,
               days_to_expiry, lot_size, available_qty, metadata):
    cfg = DEFAULT_GATE_CONFIG
    gross_buy_value = buy_price * lot_size

    def pct_cost(pct):
        return gross_buy_value * (pct / 100.0)

    return {
        "opportunity_id": f"{symbol}|{strategy}|{direction}",
        "opportunity_type": "arbitrage",
        "asset": symbol,
        "buy_market": "NSE",
        "sell_market": "NSE_FNO",
        "buy_price": buy_price,
        "sell_price": sell_price,
        "quantity": lot_size,
        "buy_settlement_days": 0,
        "sell_settlement_days": 0,
        "holding_period_days": max(days_to_expiry, 0.1),
        "annual_financing_rate_pct": 0.0,  # financing already inside fair value
        "buy_side_available_quantity": available_qty,
        "sell_side_available_quantity": available_qty,
        "buy_spread_pct": cfg["default_spread_pct"],
        "sell_spread_pct": cfg["default_spread_pct"],
        "max_participation_rate": cfg["max_participation_rate"],
        "slippage_pct_at_full_participation": cfg["slippage_pct_at_full_participation"],
        "min_fill_ratio": cfg["min_fill_ratio"],
        "min_annualized_return_pct": cfg["min_annualized_return_pct"],
        "buy_brokerage": pct_cost(cfg["buy_brokerage_pct"]),
        "sell_brokerage": pct_cost(cfg["sell_brokerage_pct"]),
        "buy_tax": pct_cost(cfg["buy_tax_pct"]),
        "sell_tax": pct_cost(cfg["sell_tax_pct"]),
        "handling_cost": pct_cost(cfg["latency_buffer_pct"]),
        "metadata": metadata
    }


def futures_basis_candidate(symbol, spot_price, future_price, days_to_expiry,
                            lot_size, available_qty=100000.0,
                            annual_rate_pct=6.0):
    if spot_price <= 0 or future_price <= 0 or days_to_expiry <= 0:
        return None
    fair = spot_price * (1.0 + (annual_rate_pct / 100.0) * days_to_expiry / 365.0)
    if future_price == fair:
        return None
    if future_price > fair:
        direction, buy_price, sell_price = "CASH_AND_CARRY", fair, future_price
    else:
        direction, buy_price, sell_price = "REVERSE_CASH_AND_CARRY", future_price, fair
    return _candidate(
        symbol, "futures_basis", direction, buy_price, sell_price,
        days_to_expiry, lot_size, available_qty,
        {"spot": spot_price, "future": future_price, "fair_future": fair,
         "basis_pct": (future_price - fair) / fair * 100.0,
         "direction": direction}
    )


def put_call_parity_candidate(symbol, spot_price, call_price, put_price,
                              strike, days_to_expiry, lot_size,
                              available_qty=100000.0, annual_rate_pct=6.0):
    if min(spot_price, call_price, put_price, strike) <= 0 or days_to_expiry <= 0:
        return None
    financed_cost = (spot_price + put_price - call_price) * (
        1.0 + (annual_rate_pct / 100.0) * days_to_expiry / 365.0
    )
    if financed_cost == strike or financed_cost <= 0:
        return None
    if strike > financed_cost:
        direction, buy_price, sell_price = "CONVERSION", financed_cost, float(strike)
    else:
        direction, buy_price, sell_price = "REVERSAL", float(strike), financed_cost
    return _candidate(
        symbol, "put_call_parity", direction, buy_price, sell_price,
        days_to_expiry, lot_size, available_qty,
        {"spot": spot_price, "call": call_price, "put": put_price,
         "strike": strike, "financed_package_cost": financed_cost,
         "parity_gap_pct": (strike - financed_cost) / financed_cost * 100.0,
         "direction": direction}
    )
