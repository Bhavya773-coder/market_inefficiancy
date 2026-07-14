"""
Live paper-trading dashboard — single page, stdlib only.

Serves:
    /            self-refreshing HTML view (fetches /api/state every 2s)
    /api/state   JSON snapshot assembled from a session directory's JSONL
                 files (quotes, detections, paper_trades)

Honesty rules baked in:
- Every quote/section carries its data_source; anything not from a live
  connector feed is tagged SIMULATED DATA in the UI.
- The health strip shows the Dhan token state (expired = BLOCKED) and
  NSE market hours for what they actually are right now.
- Paper trading is labeled PAPER everywhere — there is no real-order
  path in this codebase.

Usage:
    PYTHONPATH=. python live/dashboard_server.py \
        --session-dir storage/crypto_live_session_20260714 [--port 8720]
"""
import argparse
import base64
import json
import pathlib
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import dotenv_values

from live.run_live_paper_trading import is_market_open_now

LIVE_DATA_SOURCES = {"crypto_com_live", "dhan_live"}
QUOTE_FRESH_SECONDS = 20.0


def _read_jsonl_tail(path, max_lines=400):
    """Reads up to the last max_lines JSON records of a JSONL file."""
    p = pathlib.Path(path)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()[-max_lines:]
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _token_status(env_file=".env"):
    values = dotenv_values(env_file)
    token = (values.get("DHAN_ACCESS_TOKEN") or "").strip()
    if not token:
        return {"status": "MISSING", "detail": "no DHAN_ACCESS_TOKEN in .env"}
    parts = token.split(".")
    if len(parts) != 3:
        return {"status": "MALFORMED", "detail": "token is not a JWT"}
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        exp = payload.get("exp")
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
    except Exception:
        return {"status": "MALFORMED", "detail": "cannot decode JWT payload"}
    if exp_dt <= datetime.now(timezone.utc):
        return {"status": "EXPIRED", "detail": f"expired {exp_dt.isoformat()}"}
    return {"status": "VALID", "detail": f"expires {exp_dt.isoformat()}"}


class DashboardState:
    def __init__(self, session_dir, env_file=".env"):
        self.session_dir = pathlib.Path(session_dir)
        self.env_file = env_file

    def _quote_records(self):
        # crypto runner: quotes.jsonl | NSE runner: quote_ingestions.jsonl
        for name in ("quotes.jsonl", "quote_ingestions.jsonl"):
            records = _read_jsonl_tail(self.session_dir / name, 50)
            if records:
                return records
        return []

    def build(self):
        now = datetime.now(timezone.utc)
        quote_records = self._quote_records()
        trades = _read_jsonl_tail(self.session_dir / "paper_trades.jsonl", 400)
        detections = _read_jsonl_tail(self.session_dir / "detections.jsonl", 100)

        # ---- Quotes (latest tick) ----
        latest_quotes = {}
        last_quote_at = None
        if quote_records:
            last = quote_records[-1]
            last_quote_at = last.get("timestamp")
            for sym, q in (last.get("quotes") or {}).items():
                latest_quotes[sym] = q

        quote_age_s = None
        feed_live = False
        if last_quote_at:
            try:
                ts = datetime.fromisoformat(str(last_quote_at).replace("Z", "+00:00"))
                quote_age_s = max(0.0, (now - ts).total_seconds())
                feed_live = quote_age_s <= QUOTE_FRESH_SECONDS
            except ValueError:
                pass

        # ---- Trades / opportunities ----
        entries = [t for t in trades if t.get("type") == "entry"]
        exits = [t for t in trades if t.get("type") == "exit"]
        blocked = [t for t in trades if t.get("type") == "blocked"]
        summary = next((t for t in reversed(trades) if t.get("type") == "session_summary"), None)

        # Account state: last entry/exit carries it
        account = None
        for t in reversed(trades):
            if isinstance(t.get("account"), dict):
                account = t["account"]
                break

        positions = []
        if account:
            price_key = {}
            for sym, q in latest_quotes.items():
                lp = q.get("last_price")
                if isinstance(lp, (int, float)):
                    price_key[sym.split(":")[-1]] = lp
                    price_key[sym] = lp
            for sym, pos in (account.get("positions") or {}).items():
                mark = price_key.get(sym)
                avg = pos.get("average_price")
                qty = pos.get("quantity")
                unrealized = (mark - avg) * qty if isinstance(mark, (int, float)) else None
                positions.append({
                    "symbol": sym, "quantity": qty, "average_price": avg,
                    "mark_price": mark, "unrealized_pnl": unrealized
                })

        realized_cash = account.get("cash") if account else None
        starting_cash = account.get("starting_cash") if account else None
        mtm_value = None
        if account is not None:
            mtm_value = realized_cash + sum(
                (p["mark_price"] if p["mark_price"] is not None else p["average_price"]) * p["quantity"]
                for p in positions
            )

        # ---- Data source honesty ----
        sources_seen = set()
        for q in latest_quotes.values():
            src = q.get("data_source") or q.get("source")
            if src:
                sources_seen.add(str(src))
        is_simulated = bool(sources_seen) and not (sources_seen & LIVE_DATA_SOURCES)

        # ---- Recent opportunity flow (allowed + blocked, newest first) ----
        opportunity_rows = []
        for t in reversed(trades[-60:]):
            if t.get("type") == "entry":
                opportunity_rows.append({
                    "kind": "ENTRY", "symbol": t.get("symbol"), "price": t.get("price"),
                    "quantity": t.get("quantity"),
                    "reference": t.get("lag_reference"),
                    "gate": t.get("gate_evaluation"),
                    "timestamp": t.get("timestamp")
                })
            elif t.get("type") == "blocked":
                opportunity_rows.append({
                    "kind": "BLOCKED", "symbol": t.get("symbol"), "price": t.get("price"),
                    "reference": t.get("lag_reference"),
                    "rejection_reasons": t.get("rejection_reasons"),
                    "timestamp": t.get("timestamp")
                })
            elif t.get("type") == "exit":
                opportunity_rows.append({
                    "kind": "EXIT", "symbol": t.get("symbol"), "price": t.get("price"),
                    "timestamp": t.get("timestamp")
                })
            if len(opportunity_rows) >= 25:
                break

        # ---- Health strip ----
        token = _token_status(self.env_file)
        market_open, market_reason = is_market_open_now(now)
        health = {
            "session_feed": "LIVE" if feed_live else ("STALE" if quote_records else "NO DATA"),
            "quote_age_seconds": quote_age_s,
            "dhan_token": token,
            "nse_market": {"open": market_open, "reason": market_reason},
            "preflight_command": "PYTHONPATH=. python scripts/preflight_check.py"
        }

        return {
            "generated_at": now.isoformat(),
            "session_dir": str(self.session_dir),
            "execution_mode": "PAPER ONLY — no real orders exist in this codebase",
            "is_simulated_data": is_simulated,
            "data_sources": sorted(sources_seen),
            "health": health,
            "quotes": latest_quotes,
            "last_quote_at": last_quote_at,
            "positions": positions,
            "account": {
                "starting_cash": starting_cash,
                "cash": realized_cash,
                "mark_to_market_value": mtm_value,
                "pnl": (mtm_value - starting_cash) if (mtm_value is not None and starting_cash) else None
            },
            "counters": {
                "entries": len(entries),
                "exits": len(exits),
                "blocked": len(blocked),
                "detections_seen": len(detections)
            },
            "session_summary": summary,
            "opportunities": opportunity_rows
        }


DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Market Inefficiency Terminal — PAPER</title>
<style>
 body{background:#0d1117;color:#c9d1d9;font-family:Consolas,Menlo,monospace;margin:0;padding:16px}
 h1{font-size:18px;margin:0 0 4px} h2{font-size:13px;color:#8b949e;margin:18px 0 6px;text-transform:uppercase;letter-spacing:1px}
 .badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;margin-left:6px}
 .live{background:#123d2a;color:#3fb950}.blocked{background:#3d1214;color:#f85149}
 .warn{background:#3d2e12;color:#d29922}.sim{background:#3d1214;color:#f85149;border:1px solid #f85149}
 .paper{background:#1c2d3d;color:#58a6ff}
 table{border-collapse:collapse;width:100%;font-size:12px}
 th,td{text-align:left;padding:4px 10px;border-bottom:1px solid #21262d}
 th{color:#8b949e;font-weight:normal}
 .pos{color:#3fb950}.neg{color:#f85149}.dim{color:#8b949e}
 .kind-ENTRY{color:#3fb950}.kind-BLOCKED{color:#8b949e}.kind-EXIT{color:#58a6ff}
 #meta{font-size:11px;color:#8b949e}
</style></head><body>
<h1>MARKET INEFFICIENCY TERMINAL <span class="badge paper">PAPER EXECUTION ONLY</span><span id="simbadge"></span></h1>
<div id="meta">loading…</div>
<h2>System health</h2><table id="health"></table>
<h2>Data sources</h2><table id="sources"></table>
<h2>Live quotes</h2><table id="quotes"></table>
<h2>Opportunity flow (ranking-engine verdicts)</h2><table id="opps"></table>
<h2>Paper positions &amp; PnL</h2><table id="positions"></table>
<div id="acct" style="margin-top:6px;font-size:12px"></div>
<script>
function fmt(x,d=2){return (x===null||x===undefined)?'—':(typeof x==='number'?x.toLocaleString('en-IN',{maximumFractionDigits:d}):x)}
function cls(x){return x>0?'pos':(x<0?'neg':'dim')}
async function tick(){
 let s; try{ s = await (await fetch('/api/state')).json(); }catch(e){ document.getElementById('meta').textContent='state fetch failed: '+e; return; }
 document.getElementById('meta').textContent =
   'session: '+s.session_dir+'  |  updated '+s.generated_at+'  |  mode: '+s.execution_mode;
 document.getElementById('simbadge').innerHTML = s.is_simulated_data ?
   '<span class="badge sim">SIMULATED DATA</span>' : '';
 const h=s.health;
 document.getElementById('health').innerHTML =
  '<tr><th>Session feed</th><td><span class="badge '+(h.session_feed==='LIVE'?'live':'blocked')+'">'+h.session_feed+'</span>'+
  (h.quote_age_seconds!==null?' age '+fmt(h.quote_age_seconds,1)+'s':'')+'</td></tr>'+
  '<tr><th>Dhan token</th><td><span class="badge '+(h.dhan_token.status==='VALID'?'live':'blocked')+'">'+h.dhan_token.status+'</span> <span class="dim">'+h.dhan_token.detail+'</span></td></tr>'+
  '<tr><th>NSE market</th><td><span class="badge '+(h.nse_market.open?'live':'warn')+'">'+(h.nse_market.open?'OPEN':'CLOSED')+'</span> <span class="dim">'+h.nse_market.reason+'</span></td></tr>'+
  '<tr><th>Preflight</th><td class="dim">'+h.preflight_command+'</td></tr>';
 document.getElementById('sources').innerHTML = '<tr><th>Source</th><th>Status</th></tr>'+
  (s.data_sources.length? s.data_sources.map(d=>'<tr><td>'+d+'</td><td>'+
    (['crypto_com_live','dhan_live'].includes(d)?'<span class="badge live">REAL LIVE FEED</span>':'<span class="badge sim">SIMULATED DATA</span>')+
  '</td></tr>').join('') : '<tr><td colspan=2 class="dim">no quotes yet</td></tr>');
 document.getElementById('quotes').innerHTML = '<tr><th>Symbol</th><th>Last</th><th>Bid</th><th>Ask</th><th>Source ts</th></tr>'+
  Object.entries(s.quotes).map(([k,q])=>'<tr><td>'+k+'</td><td>'+fmt(q.last_price,4)+'</td><td class="dim">'+fmt(q.bid,4)+'</td><td class="dim">'+fmt(q.ask,4)+'</td><td class="dim">'+fmt(q.timestamp)+'</td></tr>').join('');
 document.getElementById('opps').innerHTML =
  '<tr><th>Kind</th><th>Symbol</th><th>Ref</th><th>Px</th><th>Engine breakdown / rejection</th><th>At</th></tr>'+
  (s.opportunities.length? s.opportunities.map(o=>{
    let detail='';
    if(o.kind==='ENTRY'&&o.gate) detail='net '+fmt(o.gate.net_profit_pct,3)+'% | annualized '+fmt(o.gate.annualized_return_pct,1)+'% | liq '+fmt(o.gate.liquidity_score,3)+' | rank '+fmt(o.gate.rank_score,1);
    if(o.kind==='BLOCKED') detail=(o.rejection_reasons||[]).join(', ');
    return '<tr><td class="kind-'+o.kind+'">'+o.kind+'</td><td>'+o.symbol+'</td><td class="dim">'+(o.reference||'—')+'</td><td>'+fmt(o.price,4)+'</td><td class="dim">'+detail+'</td><td class="dim">'+fmt(o.timestamp)+'</td></tr>';
  }).join('') : '<tr><td colspan=6 class="dim">no signals yet</td></tr>');
 document.getElementById('positions').innerHTML =
  '<tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>Mark</th><th>Unrealized PnL</th></tr>'+
  (s.positions.length? s.positions.map(p=>'<tr><td>'+p.symbol+'</td><td>'+fmt(p.quantity,4)+'</td><td>'+fmt(p.average_price,4)+'</td><td>'+fmt(p.mark_price,4)+'</td><td class="'+cls(p.unrealized_pnl)+'">'+fmt(p.unrealized_pnl)+'</td></tr>').join('') : '<tr><td colspan=5 class="dim">no open paper positions</td></tr>');
 const a=s.account, c=s.counters;
 document.getElementById('acct').innerHTML =
  'cash <b>'+fmt(a.cash)+'</b> | mark-to-market <b>'+fmt(a.mark_to_market_value)+'</b> | PnL <b class="'+cls(a.pnl)+'">'+fmt(a.pnl)+'</b>'+
  ' &nbsp;&nbsp; entries '+c.entries+' | exits '+c.exits+' | blocked by ranking engine '+c.blocked;
}
tick(); setInterval(tick, 2000);
</script></body></html>"""


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/state"):
                body = json.dumps(state.build(), default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            elif self.path == "/" or self.path.startswith("/index"):
                body = DASHBOARD_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
            else:
                body = b"not found"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            pass  # quiet; the runner's own logs are the record

    return Handler


def serve(session_dir, port=8720, env_file=".env"):
    state = DashboardState(session_dir, env_file=env_file)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    print(f"Dashboard: http://127.0.0.1:{port}  (session: {session_dir})")
    print("PAPER EXECUTION ONLY — Ctrl+C to stop.")
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Live paper-trading dashboard (read-only)")
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--port", type=int, default=8720)
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    serve(args.session_dir, args.port, args.env_file)


if __name__ == "__main__":
    main()
