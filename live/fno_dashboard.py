"""
F&O / spot inefficiency dashboard — KPI cards + caught-inefficiencies table +
one-click Excel export. Real trading-desk look, stdlib only.

    PYTHONPATH=. python live/fno_dashboard.py --session-dir storage/fno_session
    -> http://127.0.0.1:8730

Endpoints:
    /                self-refreshing HTML view
    /api/state       JSON snapshot
    /api/export.xlsx generates scripts/fno_session_report.py's report and
                     streams it as a download
"""
import argparse
import json
import pathlib
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.fno_session_report import build as build_fno_report

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>F&O Inefficiency Terminal — PAPER</title>
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
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}
.paper{background:rgba(76,141,255,.15);color:var(--blue)}
.y{color:var(--green);font-weight:600}.n{color:var(--muted)}
#meta{font-size:11px;color:var(--muted)}
.btn{background:var(--accent);color:#fff;border:none;padding:9px 16px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer}
.btn:hover{filter:brightness(1.15)}
.wrap{padding:20px 22px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
.kpi{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.kpi .lbl{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.kpi .val{font-size:22px;font-weight:700}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px}
.panel h2{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin:0 0 12px;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.4px}
.pos{color:var(--green)}.neg{color:var(--red)}
.strategy-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}
.strategy-card{background:var(--panel2);border:1px solid var(--border);border-radius:10px;padding:10px 12px}
.strategy-card .name{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.3px}
.strategy-card .net{font-size:17px;font-weight:700;margin-top:2px}
</style></head><body>
<div class="topbar">
  <div class="brand"><span class="dot"></span> F&amp;O / SPOT INEFFICIENCY TERMINAL <span class="badge paper">PAPER EXECUTION ONLY</span></div>
  <div style="display:flex;align-items:center;gap:10px">
    <span id="meta">loading…</span>
    <button class="btn" onclick="window.location='/api/export.xlsx'">⬇ Download Excel Report</button>
  </div>
</div>
<div class="wrap">
  <div class="kpis" id="kpis"></div>
  <div class="panel"><h2>Net Profit by Strategy (INR)</h2><div class="strategy-grid" id="strategies"></div></div>
  <div class="panel"><h2>Caught Inefficiencies — stocks, F&amp;O, commodities</h2><table id="t"></table></div>
</div>
<script>
function fmt(x,d=2){return (x===null||x===undefined)?'—':(typeof x==='number'?x.toLocaleString('en-IN',{maximumFractionDigits:d}):x)}
function cls(x){return x>0?'pos':(x<0?'neg':'')}
async function tick(){
 const s = await (await fetch('/api/state')).json();
 document.getElementById('meta').textContent = 'session: '+s.session_dir+' | updated '+new Date().toLocaleTimeString();
 document.getElementById('kpis').innerHTML = [
   ['Executable Captures', s.captures, ''],
   ['Net PnL (locked-in, INR)', fmt(s.running_pnl), cls(s.running_pnl)],
   ['Opportunities Scanned', fmt(s.total_scanned,0), ''],
   ['Executable Rate', fmt(s.total_scanned? 100*s.executable_count/s.total_scanned : 0,2)+'%', ''],
 ].map(([l,v,k])=>'<div class="kpi"><div class="lbl">'+l+'</div><div class="val '+k+'">'+v+'</div></div>').join('');
 document.getElementById('strategies').innerHTML = Object.entries(s.by_strategy||{}).map(([k,v])=>
   '<div class="strategy-card"><div class="name">'+k+'</div><div class="net '+cls(v)+'">'+fmt(v)+'</div></div>').join('');
 document.getElementById('t').innerHTML =
  '<tr><th>Time</th><th>Symbol</th><th>Strategy</th><th>Direction</th><th>Action (Buy/Sell)</th>'+
  '<th>Net edge %</th><th>Net profit INR</th><th>Executable</th></tr>' +
  s.rows.map(r=>'<tr><td>'+r.timestamp.slice(11,19)+'</td><td>'+r.asset+'</td><td>'+r.strategy+
   '</td><td>'+r.direction+'</td><td>'+(r.action||r.direction)+'</td><td>'+r.net_profit_pct.toFixed(4)+'</td><td>'+r.net_profit.toFixed(2)+
   '</td><td class="'+(r.is_executable?'y':'n')+'">'+(r.is_executable?'YES':r.rejection_reasons.join(','))+'</td></tr>').join('');
}
tick(); setInterval(tick, 5000);
</script></body></html>"""


def build_state(session_dir, max_rows=100):
    d = pathlib.Path(session_dir)

    def tail(name, n=2000):
        p = d / name
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()[-n:] if x.strip()]

    all_rows = tail("inefficiencies.jsonl")
    rows = all_rows[-max_rows:][::-1]
    trades = tail("paper_trades.jsonl")
    summary = next((t for t in reversed(trades) if t.get("type") == "session_summary"), None)
    captures = [t for t in trades if t.get("type") == "capture"]
    by_strategy = {}
    for c in captures:
        by_strategy[c["strategy"]] = by_strategy.get(c["strategy"], 0.0) + c["net_profit"]
    executable_count = sum(1 for r in all_rows if r.get("is_executable"))
    return {
        "session_dir": str(d),
        "rows": rows,
        "captures": len(captures),
        "running_pnl": sum(t["net_profit"] for t in captures),
        "total_pnl": summary["total_paper_pnl"] if summary else None,
        "total_scanned": len(all_rows),
        "executable_count": executable_count,
        "by_strategy": by_strategy,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--session-dir", required=True)
    p.add_argument("--port", type=int, default=8730)
    args = p.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/export.xlsx"):
                try:
                    path, net, n = build_fno_report(args.session_dir)
                    body = pathlib.Path(path).read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    self.send_header("Content-Disposition", f'attachment; filename="{pathlib.Path(path).name}"')
                except Exception as e:
                    body = str(e).encode("utf-8")
                    self.send_response(500)
                    self.send_header("Content-Type", "text/plain")
            elif self.path.startswith("/api/state"):
                body = json.dumps(build_state(args.session_dir), default=str).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            else:
                body = HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    print(f"F&O dashboard: http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
