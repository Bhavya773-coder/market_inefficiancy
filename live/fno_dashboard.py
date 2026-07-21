"""
Minimal F&O inefficiency dashboard: one table of caught inefficiencies +
total paper P&L. Nothing else, by design.

    PYTHONPATH=. python live/fno_dashboard.py --session-dir storage/fno_session
    -> http://127.0.0.1:8730
"""
import argparse
import json
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Inefficiencies — PAPER</title>
<style>
 body{background:#0d1117;color:#c9d1d9;font-family:Consolas,monospace;padding:16px}
 h1{font-size:16px} table{border-collapse:collapse;width:100%;font-size:12px}
 th,td{text-align:left;padding:4px 10px;border-bottom:1px solid #21262d}
 th{color:#8b949e} .y{color:#3fb950}.n{color:#8b949e}
 #pnl{margin-top:14px;font-size:15px;font-weight:bold}
</style></head><body>
<h1>CAUGHT INEFFICIENCIES — stocks, F&O, commodities (paper only)</h1>
<table id="t"><tr><th>Time</th><th>Symbol</th><th>Strategy</th><th>Direction</th><th>Action (Buy/Sell)</th>
<th>Net edge %</th><th>Net profit INR</th><th>Executable</th></tr></table>
<div id="pnl"></div>
<script>
async function tick(){
 const s = await (await fetch('/api/state')).json();
 document.getElementById('t').innerHTML =
  '<tr><th>Time</th><th>Symbol</th><th>Strategy</th><th>Direction</th><th>Action (Buy/Sell)</th><th>Net edge %</th><th>Net profit INR</th><th>Executable</th></tr>' +
  s.rows.map(r=>'<tr><td>'+r.timestamp.slice(11,19)+'</td><td>'+r.asset+'</td><td>'+r.strategy+
   '</td><td>'+r.direction+'</td><td>'+(r.action||r.direction)+'</td><td>'+r.net_profit_pct.toFixed(4)+'</td><td>'+r.net_profit.toFixed(2)+
   '</td><td class="'+(r.is_executable?'y':'n')+'">'+(r.is_executable?'YES':r.rejection_reasons.join(','))+'</td></tr>').join('');
 document.getElementById('pnl').textContent =
  'Paper P&L at close (locked-in captures): ' + (s.total_pnl===null?'session still running — '+s.captures+' captures so far, running total '+s.running_pnl.toFixed(2)+' INR':s.total_pnl.toFixed(2)+' INR ('+s.captures+' captures)');
}
tick(); setInterval(tick, 5000);
</script></body></html>"""


def build_state(session_dir, max_rows=100):
    d = pathlib.Path(session_dir)

    def tail(name):
        p = d / name
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()[-500:] if x.strip()]

    rows = [r for r in tail("inefficiencies.jsonl")][-max_rows:][::-1]
    trades = tail("paper_trades.jsonl")
    summary = next((t for t in reversed(trades) if t.get("type") == "session_summary"), None)
    captures = [t for t in trades if t.get("type") == "capture"]
    return {
        "rows": rows,
        "captures": len(captures),
        "running_pnl": sum(t["net_profit"] for t in captures),
        "total_pnl": summary["total_paper_pnl"] if summary else None
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--session-dir", required=True)
    p.add_argument("--port", type=int, default=8730)
    args = p.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/state"):
                body = json.dumps(build_state(args.session_dir), default=str).encode()
                ctype = "application/json"
            else:
                body, ctype = HTML.encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    print(f"F&O dashboard: http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
