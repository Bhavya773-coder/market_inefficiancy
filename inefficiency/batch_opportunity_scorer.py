"""
Vectorized batch scoring for OpportunityRankingEngine candidates.

Reimplements the exact evaluate() math over arrays so thousands of
candidates score in one pass. Backends:
- "numpy": vectorized CPU (always available)
- "cupy":  same code on CUDA GPU (used only if cupy imports and a
           device is present)

Parity with OpportunityRankingEngine.evaluate() is enforced by
replay/batch_opportunity_scorer_test.py — if the scalar engine changes,
that test must fail until this file is updated to match.
"""
import numpy


def _get_backend(name):
    if name == "numpy":
        return numpy
    if name == "cupy":
        import cupy  # raises if unavailable — caller decides fallback
        return cupy
    raise ValueError(f"unknown backend: {name!r} (expected 'numpy' or 'cupy')")


def gpu_available():
    """True only when cupy imports AND a CUDA device actually executes."""
    try:
        import cupy
        cupy.arange(4).sum()
        return True
    except Exception:
        return False


REASON_NAMES = [
    "liquidity_not_viable",
    "settlement_not_viable",
    "not_profitable_after_round_trip_costs",
    "insufficient_capital",
    "below_min_annualized_return"
]

FIELD_DEFAULTS = [
    # (candidate key, default)
    ("buy_price", None),
    ("sell_price", None),
    ("quantity", None),
    ("buy_settlement_days", None),
    ("sell_settlement_days", None),
    ("buy_side_available_quantity", None),
    ("sell_side_available_quantity", None),
    ("holding_period_days", 0.0),
    ("annual_financing_rate_pct", 0.0),
    ("buy_spread_pct", 0.0),
    ("sell_spread_pct", 0.0),
    ("max_participation_rate", 0.25),
    ("slippage_pct_at_full_participation", 0.5),
    ("min_fill_ratio", 1.0),
    ("min_annualized_return_pct", 0.0),
    ("buy_brokerage", 0.0),
    ("sell_brokerage", 0.0),
    ("exchange_charges", 0.0),
    ("clearing_charges", 0.0),
    ("buy_tax", 0.0),
    ("sell_tax", 0.0),
    ("gst_or_vat", 0.0),
    ("stamp_duty", 0.0),
    ("fx_spread", 0.0),
    ("freight", 0.0),
    ("warehouse_cost", 0.0),
    ("handling_cost", 0.0),
    ("hedging_cost", 0.0),
]


class BatchOpportunityScorer:

    def __init__(self, backend="numpy"):
        self.backend_name = backend
        self.xp = _get_backend(backend)

    def score(self, candidates, available_capital=None):
        """
        Scores a list of candidate dicts (same schema as
        OpportunityRankingEngine.evaluate). Returns a list of per-candidate
        dicts with the same decision fields the scalar engine produces:
        executable_quantity, capital_required, net_profit, net_profit_pct,
        annualized_return_pct, liquidity_score, rank_score, is_executable,
        rejection_reasons.
        """
        if not candidates:
            return []
        xp = self.xp
        n = len(candidates)

        cols = {}
        for key, default in FIELD_DEFAULTS:
            values = []
            for c in candidates:
                v = c.get(key, default)
                if v is None and default is None:
                    raise ValueError(f"candidate missing required key: {key}")
                values.append(float(v))
            cols[key] = xp.asarray(values, dtype=xp.float64)

        # max_acceptable_lockup_days: None -> +inf (no limit)
        cols["max_acceptable_lockup_days"] = xp.asarray(
            [float(c.get("max_acceptable_lockup_days") if c.get("max_acceptable_lockup_days") is not None else numpy.inf)
             for c in candidates], dtype=xp.float64
        )

        arrays = self.score_columns(cols, available_capital=available_capital)

        results = []
        for i, c in enumerate(candidates):
            reasons = [name for name in REASON_NAMES if bool(arrays[name][i])]
            results.append({
                "opportunity_id": c.get("opportunity_id"),
                "executable_quantity": float(arrays["executable_quantity"][i]),
                "capital_required": float(arrays["capital_required"][i]),
                "net_profit": float(arrays["net_profit"][i]),
                "net_profit_pct": float(arrays["net_profit_pct"][i]),
                "annualized_return_pct": float(arrays["annualized_return_pct"][i]),
                "liquidity_score": float(arrays["liquidity_score"][i]),
                "rank_score": float(arrays["rank_score"][i]),
                "is_executable": bool(arrays["is_executable"][i]),
                "rejection_reasons": reasons
            })
        return results

    def score_columns(self, cols, available_capital=None):
        """
        Array-native scoring: `cols` is a dict of equal-length arrays (or
        lists) keyed by the FIELD_DEFAULTS names plus
        max_acceptable_lockup_days (use +inf for 'no limit'). Returns a
        dict of result arrays on the host. This is the path where batch/
        GPU execution actually pays — no per-candidate dict handling.
        """
        xp = self.xp
        cols = {k: xp.asarray(v, dtype=xp.float64) for k, v in cols.items()}
        lockup_limits = cols["max_acceptable_lockup_days"]

        # ---- Liquidity engine (vectorized) ----
        part = cols["max_participation_rate"]
        max_buy_qty = cols["buy_side_available_quantity"] * part
        max_sell_qty = cols["sell_side_available_quantity"] * part
        exec_qty = xp.minimum(cols["quantity"], xp.minimum(max_buy_qty, max_sell_qty))
        fill_ratio = exec_qty / cols["quantity"]

        buy_participation = xp.where(
            cols["buy_side_available_quantity"] > 0,
            exec_qty / xp.maximum(cols["buy_side_available_quantity"], 1e-300),
            0.0
        )
        sell_participation = xp.where(
            cols["sell_side_available_quantity"] > 0,
            exec_qty / xp.maximum(cols["sell_side_available_quantity"], 1e-300),
            0.0
        )
        slip_full = cols["slippage_pct_at_full_participation"]
        buy_slip = (buy_participation / part) * slip_full
        sell_slip = (sell_participation / part) * slip_full
        total_liq_cost_pct = cols["buy_spread_pct"] + cols["sell_spread_pct"] + buy_slip + sell_slip
        liq_score = fill_ratio * (1.0 / (1.0 + total_liq_cost_pct))
        meets_fill = fill_ratio >= cols["min_fill_ratio"]
        liq_viable = meets_fill & (exec_qty > 0)

        # ---- Settlement engine (vectorized) ----
        capital_required = cols["buy_price"] * exec_qty
        lockup_days = cols["holding_period_days"] + cols["sell_settlement_days"]
        financing = capital_required * (cols["annual_financing_rate_pct"] / 100.0 / 365.0) * lockup_days
        settlement_viable = lockup_days <= lockup_limits

        # ---- Round-trip cost engine (vectorized) ----
        gross_buy = cols["buy_price"] * exec_qty
        gross_sell = cols["sell_price"] * exec_qty
        gross_spread = gross_sell - gross_buy
        slippage_cost = gross_buy * (total_liq_cost_pct / 100.0)
        fixed_costs = (
            cols["buy_brokerage"] + cols["sell_brokerage"] + cols["exchange_charges"]
            + cols["clearing_charges"] + cols["buy_tax"] + cols["sell_tax"]
            + cols["gst_or_vat"] + cols["stamp_duty"] + cols["fx_spread"]
            + cols["freight"] + cols["warehouse_cost"] + cols["handling_cost"]
            + cols["hedging_cost"]
        )
        total_cost = fixed_costs + slippage_cost + financing
        net_profit = gross_spread - total_cost
        net_profit_pct = xp.where(gross_buy > 0, net_profit / xp.maximum(gross_buy, 1e-300) * 100.0, 0.0)
        profitable = net_profit > 0

        # ---- Capital engine (vectorized) ----
        roc_pct = xp.where(capital_required > 0, net_profit / xp.maximum(capital_required, 1e-300) * 100.0, 0.0)
        eff_lockup = xp.maximum(lockup_days, 1.0)
        annualized = roc_pct * (365.0 / eff_lockup)
        if available_capital is None:
            can_fund = xp.ones(capital_required.shape[0], dtype=bool)
        else:
            can_fund = capital_required <= float(available_capital)
        meets_return = annualized >= cols["min_annualized_return_pct"]

        is_executable = liq_viable & settlement_viable & profitable & can_fund & meets_return
        rank_score = annualized * liq_score

        # Pull back to host (no-op for numpy)
        def host(a):
            return a.get() if hasattr(a, "get") else a

        return {
            "executable_quantity": host(exec_qty),
            "capital_required": host(capital_required),
            "net_profit": host(net_profit),
            "net_profit_pct": host(net_profit_pct),
            "annualized_return_pct": host(annualized),
            "liquidity_score": host(liq_score),
            "rank_score": host(rank_score),
            "is_executable": host(is_executable),
            "liquidity_not_viable": host(~liq_viable),
            "settlement_not_viable": host(~settlement_viable),
            "not_profitable_after_round_trip_costs": host(~profitable),
            "insufficient_capital": host(~can_fund),
            "below_min_annualized_return": host(~meets_return)
        }
