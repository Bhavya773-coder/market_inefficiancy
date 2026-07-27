"""
Compare how a session would have performed at different capital levels.

Dhan's quote endpoint rate-limits hard enough that two live sessions cannot
run side by side — a second one degrades both into retry loops. This gets the
comparison from a single session instead, which is also strictly more honest:
both capital levels are scored against the very same quotes at the very same
instants, whereas two parallel sessions would each see different ticks.

This works because available_capital only ever decides one thing in
OpportunityRankingEngine: whether capital_required fits. Profitability,
liquidity, spread and annualized return are all computed before capital is
considered, so a row is executable at capital C exactly when
    (rejection_reasons - {"insufficient_capital"}) is empty
    and capital_required <= C

    PYTHONPATH=. python scripts/capital_comparison.py \
        --session-dir storage/fno_10lakh_20260727 \
        --capitals 100000 1000000
"""
import argparse
import json
import pathlib
from collections import defaultdict

CAPITAL_REASON = "insufficient_capital"


def load(session_dir):
    p = pathlib.Path(session_dir) / "inefficiencies.jsonl"
    if not p.exists():
        raise SystemExit(f"no inefficiencies.jsonl in {session_dir}")
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def qualifies(row, capital):
    """Executable at `capital`, ignoring the capital verdict actually logged."""
    other = set(row.get("rejection_reasons") or []) - {CAPITAL_REASON}
    if other:
        return False
    need = row.get("capital_required")
    if need is None:
        return None  # pre-dates capital_required logging
    return need <= capital


def report(rows, capitals):
    missing = sum(1 for r in rows if r.get("capital_required") is None)
    if missing:
        print(f"WARNING: {missing}/{len(rows)} rows predate capital_required "
              f"logging and are excluded. Restart the session to log it.\n")
    usable = [r for r in rows if r.get("capital_required") is not None]
    if not usable:
        raise SystemExit("No rows carry capital_required yet — nothing to compare.")

    print(f"{len(usable)} scored opportunities\n")
    header = f"{'capital (INR)':>16}{'qualifying':>12}{'total net INR':>16}{'per-strategy'}"
    print(header)
    print("-" * (len(header) + 30))
    for cap in sorted(capitals):
        hits = [r for r in usable if qualifies(r, cap)]
        by_strat = defaultdict(float)
        for r in hits:
            by_strat[r["strategy"]] += r["net_profit"]
        strat_txt = ", ".join(f"{k}={v:,.0f}" for k, v in sorted(by_strat.items())) or "-"
        total = sum(r["net_profit"] for r in hits)
        print(f"{cap:>16,}{len(hits):>12}{total:>16,.2f}  {strat_txt}")

    # What the extra capital actually buys, named concretely.
    lo, hi = min(capitals), max(capitals)
    if lo != hi:
        unlocked = [r for r in usable if qualifies(r, hi) and not qualifies(r, lo)]
        print(f"\nUnlocked by going {lo:,} -> {hi:,}: {len(unlocked)} opportunities, "
              f"{sum(r['net_profit'] for r in unlocked):,.2f} INR")
        by_strat = defaultdict(lambda: [0, 0.0])
        for r in unlocked:
            by_strat[r["strategy"]][0] += 1
            by_strat[r["strategy"]][1] += r["net_profit"]
        for s, (n, net) in sorted(by_strat.items()):
            print(f"    {s:18} {n:>5} opps  {net:>12,.2f} INR")
        if unlocked:
            need = [r["capital_required"] for r in unlocked]
            print(f"    capital needed: min {min(need):,.0f}  median "
                  f"{sorted(need)[len(need)//2]:,.0f}  max {max(need):,.0f}")

    print("\nNote: these are per-opportunity gate verdicts, not a portfolio "
          "simulation — the same opportunity recurring across polls is counted "
          "each time, exactly as the live capture log does.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--session-dir", required=True)
    p.add_argument("--capitals", type=float, nargs="+",
                   default=[100000, 1000000])
    args = p.parse_args()
    report(load(args.session_dir), args.capitals)


if __name__ == "__main__":
    main()
