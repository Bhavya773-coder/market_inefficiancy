"""
Live paper-trading dashboard — single page, stdlib only.

Serves:
    /                self-refreshing HTML view (fetches /api/state every 2s)
    /api/state       JSON snapshot assembled from a session directory's JSONL
                     files (quotes, detections, paper_trades)
    /api/export.xlsx generates the same Executive Summary + Trade Details
                     report as scripts/crypto_session_report.py and streams
                     it as a download

Honesty rules baked in:
- Every quote/section carries its data_source; anything not from a live
  connector feed is tagged SIMULATED DATA in the UI.
- The health strip shows the Dhan token state (expired = BLOCKED) and
  NSE market hours for what they actually are right now.
- Paper trading is labeled PAPER everywhere — there is no real-order
  path in this codebase.
- All prices/PnL here are USDT (USD-pegged), never rupees.

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
from scripts.crypto_session_report import build as build_crypto_report

LIVE_DATA_SOURCES = {"crypto_com_live", "dhan_live"}
QUOTE_FRESH_SECONDS = 20.0
HISTORY_TICKS = 120


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

    def _quote_records(self, max_lines=HISTORY_TICKS):
        # crypto runner: quotes.jsonl | NSE runner: quote_ingestions.jsonl
        for name in ("quotes.jsonl", "quote_ingestions.jsonl"):
            records = _read_jsonl_tail(self.session_dir / name, max_lines)
            if records:
                return records
        return []

    def build(self):
        now = datetime.now(timezone.utc)
        quote_records = self._quote_records()
        trades = _read_jsonl_tail(self.session_dir / "paper_trades.jsonl", 400)
        # 400: detections now interleave lag_signal, poll_error and the
        # periodic kronos_forecast records, so a short tail can drop the most
        # recent forecast for a quiet instrument.
        detections = _read_jsonl_tail(self.session_dir / "detections.jsonl", 400)

        # ---- Quotes (latest tick + sparkline history per symbol) ----
        latest_quotes = {}
        history = {}
        last_quote_at = None
        if quote_records:
            last = quote_records[-1]
            last_quote_at = last.get("timestamp")
            for sym, q in (last.get("quotes") or {}).items():
                latest_quotes[sym] = q
            for rec in quote_records:
                for sym, q in (rec.get("quotes") or {}).items():
                    lp = q.get("last_price")
                    if isinstance(lp, (int, float)):
                        history.setdefault(sym, []).append(lp)

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
                    "reference": t.get("lag_reference") or (
                        "kronos" if t.get("source") == "kronos" else None),
                    "gate": t.get("gate_evaluation"),
                    "kronos": t.get("kronos"),
                    "timestamp": t.get("timestamp")
                })
            elif t.get("type") == "blocked":
                opportunity_rows.append({
                    "kind": "BLOCKED", "symbol": t.get("symbol"), "price": t.get("price"),
                    "reference": t.get("lag_reference") or (
                        "kronos" if t.get("source") == "kronos" else None),
                    "rejection_reasons": t.get("rejection_reasons"),
                    "kronos": t.get("kronos"),
                    "timestamp": t.get("timestamp")
                })
            elif t.get("type") == "exit":
                opportunity_rows.append({
                    "kind": "EXIT", "symbol": t.get("symbol"), "price": t.get("price"),
                    "timestamp": t.get("timestamp")
                })
            if len(opportunity_rows) >= 25:
                break

        # ---- Kronos filter telemetry ----
        # Read-only: whatever the runner already logged. The dashboard never
        # runs the model itself, so it cannot slow the trading loop down.
        # Decisions come from paper_trades (Kronos consulted at entry time);
        # the live per-instrument view comes from the runner's periodic
        # kronos_forecast telemetry in detections.
        # Filter consultations only: Kronos-originated rows are counted
        # separately as led_entries/below_cost_floor, and lumping them in here
        # made the "at entry" badge read wildly higher than actual lag entries.
        kronos_rows = [t for t in trades
                       if t.get("kronos") and t.get("source") != "kronos"]
        kronos_blocks = [t for t in trades
                         if t.get("type") == "blocked"
                         and "kronos_forecast_disagrees" in (t.get("rejection_reasons") or [])]
        latest_kronos = {}
        charts = {}
        for d in detections:
            if d.get("type") == "kronos_forecast" and d.get("symbol") and d.get("kronos"):
                k = d["kronos"]
                latest_kronos[d["symbol"]] = {
                    "up": k.get("up"), "move_pct": k.get("move_pct"),
                    "horizon": k.get("horizon"), "at": d.get("timestamp"),
                    "source": "live",
                }
                # Chart series: actual candle closes then the forecast path.
                # Kept separate from latest_kronos so the trade-decision
                # override below cannot wipe out a symbol's chart.
                if k.get("context") and k.get("path"):
                    charts[d["symbol"]] = {
                        "actual": k["context"],
                        "predicted": k["path"],
                        "last_close": k.get("last_close"),
                        "move_pct": k.get("move_pct"),
                        "up": k.get("up"),
                        "at": d.get("timestamp"),
                        "timeframe_min": 1,
                    }
        # Entry-time forecasts still win for a symbol, being tied to a decision.
        for t in trades:
            if t.get("kronos") and t.get("symbol"):
                latest_kronos[t["symbol"]] = dict(t["kronos"], at=t.get("timestamp"),
                                                  source=t.get("type"))
        kronos = {
            "consulted": len(kronos_rows),
            "vetoed_entries": len(kronos_blocks),
            "agreed": sum(1 for t in kronos_rows if t["kronos"].get("up")),
            # Entries Kronos originated on its own, with no lag event.
            "led_entries": sum(1 for t in trades if t.get("source") == "kronos"
                               and t.get("type") == "entry"),
            "below_cost_floor": sum(
                1 for t in trades if t.get("source") == "kronos"
                and t.get("type") == "blocked"
                and not set(t.get("rejection_reasons") or []) - {
                    "kronos_move_below_min", "kronos_forecast_down_long_only",
                    "not_profitable_after_round_trip_costs",
                    "below_min_annualized_return"}),
            "latest": latest_kronos,
            "charts": charts,
        }

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
            "currency": "USDT",
            "is_simulated_data": is_simulated,
            "data_sources": sorted(sources_seen),
            "health": health,
            "quotes": latest_quotes,
            "history": history,
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
            "kronos": kronos,
            "opportunities": opportunity_rows
        }


DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Crypto Lag Terminal — PAPER</title>
<style>
:root{
  --bg:#0a0e17; --panel:#121826; --panel2:#161d2e; --border:#232b3d;
  --text:#e6e9ef; --muted:#7d8aa3; --green:#20c997; --red:#f0466e;
  --blue:#4c8dff; --amber:#f5a524; --accent:#7c6cf0;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:0}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:14px 22px;border-bottom:1px solid var(--border);background:linear-gradient(180deg,#0d1220,#0a0e17)}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:16px;letter-spacing:.3px}
.brand .dot{width:9px;height:9px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green)}
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;letter-spacing:.3px}
.live{background:rgba(32,201,151,.15);color:var(--green)}.blocked{background:rgba(240,70,110,.15);color:var(--red)}
.warn{background:rgba(245,165,36,.15);color:var(--amber)}.sim{background:rgba(240,70,110,.15);color:var(--red);border:1px solid var(--red)}
.paper{background:rgba(76,141,255,.15);color:var(--blue)}
.topbar-right{display:flex;align-items:center;gap:10px}
#meta{font-size:11px;color:var(--muted)}
.btn{background:var(--accent);color:#fff;border:none;padding:9px 16px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;letter-spacing:.2px;transition:filter .15s}
.btn:hover{filter:brightness(1.15)}
.wrap{padding:20px 22px}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
.kpi{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.kpi .lbl{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.kpi .val{font-size:22px;font-weight:700}
.grid2{display:grid;grid-template-columns:2.2fr 1fr;gap:16px;align-items:start}
@media(max-width:1250px){.grid2{grid-template-columns:1fr}}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px}
.chart{background:var(--panel2);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.chart-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.chart-head .s{font-size:14px;font-weight:700}
.chart-head .p{font-size:13px}
.chart canvas{width:100%;height:190px;display:block}
.chart-foot{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:6px}
.legend{display:flex;gap:16px;align-items:center;font-size:11px;color:var(--muted);margin-bottom:12px;flex-wrap:wrap}
.legend .sw{display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:5px;vertical-align:middle}
.legend .sw.dash{background:repeating-linear-gradient(90deg,#f5a524 0 4px,transparent 4px 7px)!important}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px}
.panel h2{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin:0 0 12px;font-weight:600}
.tickers{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.ticker{background:var(--panel2);border:1px solid var(--border);border-radius:10px;padding:10px 12px}
.ticker .sym{font-size:12px;color:var(--muted);font-weight:600}
.ticker .px{font-size:17px;font-weight:700;margin:2px 0}
.ticker canvas{width:100%;height:28px;display:block;margin-top:4px}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.4px}
.pos{color:var(--green)}.neg{color:var(--red)}.dim{color:var(--muted)}
.kind-ENTRY{color:var(--green);font-weight:600}.kind-BLOCKED{color:var(--muted)}.kind-EXIT{color:var(--blue);font-weight:600}
.acct-line{display:flex;gap:22px;font-size:12.5px;color:var(--muted);flex-wrap:wrap}
.acct-line b{color:var(--text)}
</style></head><body>
<div class="topbar">
  <div class="brand"><span class="dot"></span> CRYPTO LAG TERMINAL <span class="badge paper">PAPER EXECUTION ONLY</span><span id="simbadge"></span></div>
  <div class="topbar-right">
    <span id="meta">loading…</span>
    <button class="btn" onclick="window.location='/api/export.xlsx'">⬇ Download Excel Report</button>
  </div>
</div>
<div class="wrap">
  <div class="kpis" id="kpis"></div>
  <div class="grid2">
    <div>
      <div class="panel"><h2>Live Quotes (USDT)</h2><div class="tickers" id="tickers"></div></div>
      <div class="panel"><h2>Kronos Forecast Charts <span id="kstat" class="badge"></span></h2>
        <div class="legend">
          <span><i class="sw" style="background:#4c8dff"></i>actual price</span>
          <span><i class="sw dash" style="background:#f5a524"></i>Kronos forecast</span>
          <span><i class="sw" style="background:#7d8aa3"></i>now divider</span>
          <span class="dim">forecast horizon 15m &nbsp;·&nbsp; 1m candles</span>
        </div>
        <div id="kronos-empty" class="dim" style="font-size:12px">No forecasts logged yet — either the filter is off, or no cost-gate-approved signal has needed one.</div>
        <div class="charts" id="kronos-charts"></div></div>
      <div class="panel"><h2>Opportunity Flow — ranking-engine verdicts</h2><table id="opps"></table></div>
    </div>
    <div>
      <div class="panel"><h2>System Health</h2><table id="health"></table></div>
      <div class="panel"><h2>Data Sources</h2><table id="sources"></table></div>
      <div class="panel"><h2>Paper Positions</h2><table id="positions"></table></div>
    </div>
  </div>
</div>
<script>
function fmt(x,d=2){return (x===null||x===undefined)?'—':(typeof x==='number'?x.toLocaleString('en-US',{maximumFractionDigits:d}):x)}
function cls(x){return x>0?'pos':(x<0?'neg':'dim')}
function spark(canvas, arr){
  if(!arr||arr.length<2) return;
  const ctx=canvas.getContext('2d'); const w=canvas.width=canvas.clientWidth*2, h=canvas.height=56;
  const min=Math.min(...arr), max=Math.max(...arr), range=(max-min)||1;
  const up = arr[arr.length-1] >= arr[0];
  ctx.clearRect(0,0,w,h);
  ctx.beginPath(); ctx.lineWidth=3; ctx.strokeStyle = up ? '#20c997' : '#f0466e';
  arr.forEach((v,i)=>{ const x=i/(arr.length-1)*w, y=h-((v-min)/range)*h*0.8-h*0.1; i===0?ctx.moveTo(x,y):ctx.lineTo(x,y); });
  ctx.stroke();
}

// Actual price then the Kronos forecast on one shared axis. The forecast is
// drawn dashed/amber and starts at the last actual point so the join is
// continuous and a reader can tell prediction from history at a glance.
function drawForecast(canvas, actual, predicted){
  const DPR=2, w=canvas.width=canvas.clientWidth*DPR, h=canvas.height=190*DPR;
  const ctx=canvas.getContext('2d'); ctx.clearRect(0,0,w,h);
  if(!actual||actual.length<2||!predicted||!predicted.length) return;
  const padL=58*DPR, padR=10*DPR, padT=12*DPR, padB=20*DPR;
  const plotW=w-padL-padR, plotH=h-padT-padB;
  const all=actual.concat(predicted);
  let min=Math.min(...all), max=Math.max(...all);
  const pad=((max-min)||Math.abs(max)*0.001||1)*0.12; min-=pad; max+=pad;
  const n=actual.length+predicted.length;
  const X=i=>padL+(i/(n-1))*plotW;
  const Y=v=>padT+plotH-((v-min)/(max-min))*plotH;

  // grid + y labels
  ctx.strokeStyle='rgba(125,138,163,.18)'; ctx.lineWidth=1*DPR;
  ctx.fillStyle='#7d8aa3'; ctx.font=(10*DPR)+'px ui-monospace,Consolas,monospace';
  ctx.textAlign='right'; ctx.textBaseline='middle';
  for(let g=0;g<=4;g++){
    const v=min+(max-min)*g/4, y=Y(v);
    ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(w-padR,y); ctx.stroke();
    ctx.fillText(v.toLocaleString('en-US',{maximumFractionDigits:v<10?4:2}), padL-6*DPR, y);
  }

  // actual
  ctx.beginPath(); ctx.lineWidth=2.2*DPR; ctx.strokeStyle='#4c8dff'; ctx.setLineDash([]);
  actual.forEach((v,i)=>{ i?ctx.lineTo(X(i),Y(v)):ctx.moveTo(X(i),Y(v)); });
  ctx.stroke();

  // "now" divider at the hand-off point
  const jx=X(actual.length-1);
  ctx.beginPath(); ctx.setLineDash([3*DPR,3*DPR]); ctx.lineWidth=1.4*DPR;
  ctx.strokeStyle='rgba(125,138,163,.55)';
  ctx.moveTo(jx,padT); ctx.lineTo(jx,padT+plotH); ctx.stroke();
  ctx.setLineDash([]); ctx.textAlign='left'; ctx.textBaseline='top';
  ctx.fillStyle='#7d8aa3'; ctx.fillText('now', jx+4*DPR, padT+2*DPR);

  // forecast, continuous from the last actual point
  const up=predicted[predicted.length-1]>=actual[actual.length-1];
  const fc=up?'#20c997':'#f0466e';
  ctx.beginPath(); ctx.setLineDash([6*DPR,4*DPR]); ctx.lineWidth=2.4*DPR;
  ctx.strokeStyle='#f5a524';
  ctx.moveTo(jx,Y(actual[actual.length-1]));
  predicted.forEach((v,i)=>ctx.lineTo(X(actual.length+i),Y(v)));
  ctx.stroke(); ctx.setLineDash([]);

  // shade the forecast region so it reads as "not yet real"
  ctx.fillStyle='rgba(245,165,36,.07)';
  ctx.fillRect(jx,padT,padL+plotW-jx,plotH);

  // endpoint marker, coloured by predicted direction
  const ex=X(n-1), ey=Y(predicted[predicted.length-1]);
  ctx.beginPath(); ctx.fillStyle=fc; ctx.arc(ex,ey,3.6*DPR,0,Math.PI*2); ctx.fill();
}
async function tick(){
 let s; try{ s = await (await fetch('/api/state')).json(); }catch(e){ document.getElementById('meta').textContent='state fetch failed: '+e; return; }
 document.getElementById('meta').textContent =
   'session: '+s.session_dir+'  |  updated '+s.generated_at.slice(11,19)+' UTC  |  '+s.execution_mode;
 document.getElementById('simbadge').innerHTML = s.is_simulated_data ?
   '<span class="badge sim">SIMULATED DATA</span>' : '';

 const a=s.account, c=s.counters;
 document.getElementById('kpis').innerHTML = [
   ['Cash (USDT)', fmt(a.cash), ''],
   ['Mark-to-Market', fmt(a.mark_to_market_value), ''],
   ['Total PnL', fmt(a.pnl), cls(a.pnl)],
   ['Entries / Exits', c.entries+' / '+c.exits, ''],
   ['Blocked by Engine', c.blocked, 'dim'],
 ].map(([l,v,k])=>'<div class="kpi"><div class="lbl">'+l+'</div><div class="val '+k+'">'+v+'</div></div>').join('');

 const h=s.health;
 document.getElementById('health').innerHTML =
  '<tr><th>Session feed</th><td><span class="badge '+(h.session_feed==='LIVE'?'live':'blocked')+'">'+h.session_feed+'</span>'+
  (h.quote_age_seconds!==null?' <span class="dim">age '+fmt(h.quote_age_seconds,1)+'s</span>':'')+'</td></tr>'+
  '<tr><th>Dhan token</th><td><span class="badge '+(h.dhan_token.status==='VALID'?'live':'blocked')+'">'+h.dhan_token.status+'</span></td></tr>'+
  '<tr><th>NSE market</th><td><span class="badge '+(h.nse_market.open?'live':'warn')+'">'+(h.nse_market.open?'OPEN':'CLOSED')+'</span></td></tr>';

 document.getElementById('sources').innerHTML =
  (s.data_sources.length? s.data_sources.map(d=>'<tr><td>'+d+'</td><td>'+
    (['crypto_com_live','dhan_live'].includes(d)?'<span class="badge live">LIVE FEED</span>':'<span class="badge sim">SIMULATED</span>')+
  '</td></tr>').join('') : '<tr><td class="dim">no quotes yet</td></tr>');

 document.getElementById('tickers').innerHTML = Object.entries(s.quotes).map(([k,q])=>
   '<div class="ticker"><div class="sym">'+k+'</div><div class="px">'+fmt(q.last_price,4)+'</div><canvas id="spark-'+k+'"></canvas></div>').join('');
 Object.entries(s.history||{}).forEach(([k,arr])=>{
   const el=document.getElementById('spark-'+k); if(el) spark(el, arr);
 });

 const k=s.kronos||{consulted:0,latest:{}};
 const kEntries0=Object.entries(k.latest||{});
 document.getElementById('kstat').innerHTML =
   (kEntries0.length? '<span class="badge live">'+kEntries0.length+' live</span> ':'')+
   (k.led_entries? '&nbsp;<span class="badge live">'+k.led_entries+' kronos entries</span>':'')+
   (k.below_cost_floor? '&nbsp;<span class="badge warn">'+k.below_cost_floor+' below cost floor</span>':'')+
   (k.consulted? '&nbsp;<span class="badge paper">'+k.consulted+' at entry</span> &nbsp;<span class="badge blocked">'+k.vetoed_entries+' vetoed</span>':'');
 const charts=Object.entries(k.charts||{});
 document.getElementById('kronos-empty').style.display = charts.length? 'none':'block';
 const host=document.getElementById('kronos-charts');
 // Rebuild only when the symbol set changes, so redrawing every 2s does not
 // discard canvases (and scroll position) on every tick.
 const sig=charts.map(([s])=>s).join(',');
 if(host.dataset.sig!==sig){
   host.dataset.sig=sig;
   host.innerHTML=charts.map(([sym])=>
     '<div class="chart"><div class="chart-head"><span class="s">'+sym+'</span>'+
     '<span class="p" id="ch-p-'+sym+'"></span></div>'+
     '<canvas id="ch-'+sym+'"></canvas>'+
     '<div class="chart-foot"><span id="ch-f1-'+sym+'"></span><span id="ch-f2-'+sym+'"></span></div></div>').join('');
 }
 charts.forEach(([sym,c])=>{
   const cv=document.getElementById('ch-'+sym); if(!cv) return;
   drawForecast(cv, c.actual, c.predicted);
   const pred=c.predicted[c.predicted.length-1];
   document.getElementById('ch-p-'+sym).innerHTML =
     '<span class="dim">now</span> '+fmt(c.last_close,4)+
     ' <span class="dim">→</span> <span class="'+(c.up?'pos':'neg')+'">'+fmt(pred,4)+
     ' ('+(c.up?'+':'')+fmt(c.move_pct,3)+'%)</span>';
   document.getElementById('ch-f1-'+sym).textContent =
     c.actual.length+'m actual · '+c.predicted.length+'m forecast';
   document.getElementById('ch-f2-'+sym).textContent =
     c.at? 'forecast at '+String(c.at).slice(11,19)+' UTC' : '';
 });

 document.getElementById('opps').innerHTML =
  '<tr><th>Kind</th><th>Symbol</th><th>Ref</th><th>Px</th><th>Kronos</th><th>Engine breakdown / rejection</th><th>At</th></tr>'+
  (s.opportunities.length? s.opportunities.map(o=>{
    let detail='';
    if(o.kind==='ENTRY'&&o.gate) detail='net '+fmt(o.gate.net_profit_pct,3)+'% | ann '+fmt(o.gate.annualized_return_pct,1)+'% | liq '+fmt(o.gate.liquidity_score,3);
    if(o.kind==='BLOCKED') detail=(o.rejection_reasons||[]).join(', ');
    const kc = o.kronos
      ? '<span class="'+(o.kronos.up?'pos':'neg')+'">'+(o.kronos.up?'▲':'▼')+' '+fmt(o.kronos.move_pct,3)+'%</span>'
      : '<span class="dim">—</span>';
    return '<tr><td class="kind-'+o.kind+'">'+o.kind+'</td><td>'+o.symbol+'</td><td class="dim">'+(o.reference||'—')+'</td><td>'+fmt(o.price,4)+'</td><td>'+kc+'</td><td class="dim">'+detail+'</td><td class="dim">'+fmt(o.timestamp).slice(11,19)+'</td></tr>';
  }).join('') : '<tr><td colspan=7 class="dim">no signals yet</td></tr>');

 document.getElementById('positions').innerHTML =
  '<tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>Mark</th><th>Unrl. PnL</th></tr>'+
  (s.positions.length? s.positions.map(p=>'<tr><td>'+p.symbol+'</td><td>'+fmt(p.quantity,4)+'</td><td>'+fmt(p.average_price,4)+'</td><td>'+fmt(p.mark_price,4)+'</td><td class="'+cls(p.unrealized_pnl)+'">'+fmt(p.unrealized_pnl)+'</td></tr>').join('') : '<tr><td colspan=5 class="dim">no open paper positions</td></tr>');
}
tick(); setInterval(tick, 2000);
</script></body></html>"""


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/export.xlsx"):
                try:
                    path, net, n = build_crypto_report(str(state.session_dir))
                    body = pathlib.Path(path).read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    self.send_header("Content-Disposition", f'attachment; filename="{pathlib.Path(path).name}"')
                except Exception as e:
                    body = str(e).encode("utf-8")
                    self.send_response(500)
                    self.send_header("Content-Type", "text/plain")
            elif self.path.startswith("/api/state"):
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
