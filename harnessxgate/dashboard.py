#!/usr/bin/env python3
"""HarnessXGate Live Web Dashboard — Python stdlib only, zero external assets, beginner-friendly."""

from __future__ import annotations

import http.server
import json
import threading
import time
import urllib.parse
from typing import Any

from harnessxgate import __version__, router

_HEALTH_LOCK = threading.Lock()
_health_cache: dict[str, Any] = {"t": 0.0, "data": None}
MAX_POST_BYTES = 262_144  # 256 KiB


def get_health(*, force: bool = False) -> dict[str, Any]:
    with _HEALTH_LOCK:
        if not force and _health_cache["data"] is not None and time.time() - _health_cache["t"] < 20.0:
            return _health_cache["data"]
    try:
        data = router.check_all_health()
    except Exception as exc:  # noqa: BLE001
        data = {"error": str(exc)}
    with _HEALTH_LOCK:
        _health_cache["t"] = time.time()
        _health_cache["data"] = data
    return data


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HarnessXGate · Free AI Fleet Dashboard</title>
<style>
  :root{
    --bg:#0b0b0c;--panel:#141416;--panel2:#1b1b1f;--line:#27272c;--fg:#eceae6;--muted:#94908a;
    --gold:#e0b07a;--gold-soft:rgba(224,176,122,.14);--green:#5ec488;--green-soft:rgba(94,196,136,.14);
    --red:#e06c75;--red-soft:rgba(224,108,117,.14);--amber:#e5b567;--amber-soft:rgba(229,181,103,.14);
    --radius:10px;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);
       font:14px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
  header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:14px;
         padding:20px 28px;border-bottom:1px solid var(--line);background:#0f0f11;position:sticky;top:0;z-index:5}
  .brand{display:flex;align-items:baseline;gap:12px}
  h1{margin:0;font:600 24px/1.1 Georgia,"Times New Roman",serif;letter-spacing:.3px;color:var(--fg)}
  .ver{font-size:11px;padding:2px 8px;border-radius:99px;background:var(--gold-soft);color:var(--gold);font-weight:600}
  .tag{color:var(--muted);font-size:12px}
  .actions{display:flex;gap:8px;flex-wrap:wrap}
  button{cursor:pointer;border:1px solid var(--line);background:var(--panel2);color:var(--fg);
         padding:7px 13px;border-radius:7px;font:500 12px/1.2 inherit;transition:.15s}
  button:hover{border-color:var(--gold);color:var(--gold)}
  button.primary{background:var(--gold);color:#141210;border-color:var(--gold);font-weight:600}
  button.primary:hover{filter:brightness(1.08);color:#141210}
  button:disabled{opacity:.5;cursor:not-allowed}
  main{padding:22px 28px 64px;max-width:1200px;margin:0 auto}
  .section-head{display:flex;align-items:center;justify-content:space-between;margin:26px 0 10px}
  h2{font:600 12px/1.2 inherit;letter-spacing:1.5px;text-transform:uppercase;color:var(--gold);margin:0}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:15px 17px}
  .card .top{display:flex;align-items:center;justify-content:space-between;gap:8px}
  .card .name{font-size:12px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);font-weight:600}
  .badge{font-size:11px;padding:2px 8px;border-radius:99px;font-weight:600;white-space:nowrap}
  .badge.ok{background:var(--green-soft);color:var(--green)}
  .badge.warn{background:var(--amber-soft);color:var(--amber)}
  .badge.err{background:var(--red-soft);color:var(--red)}
  .badge.muted{background:#222227;color:var(--muted)}
  .card .status{margin-top:8px;font-size:18px;font-weight:600;color:var(--fg)}
  .card .meta{margin-top:5px;font-size:12px;color:var(--muted);word-break:break-word}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--muted);margin-right:7px;vertical-align:middle}
  .dot.on{background:var(--green);box-shadow:0 0 8px var(--green)}
  .dot.warn{background:var(--amber)}
  .dot.off{background:var(--red)}
  .ask-box{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px}
  .ask-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px;align-items:center}
  select{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:7px;padding:7px 10px;font:13px inherit}
  textarea{width:100%;min-height:76px;resize:vertical;background:#0e0e10;color:var(--fg);
           border:1px solid var(--line);border-radius:8px;padding:10px 12px;font:14px/1.5 inherit}
  textarea:focus,select:focus{outline:none;border-color:var(--gold)}
  .reply-box{margin-top:12px;padding:12px 14px;border-radius:8px;background:#0e0e10;border:1px solid var(--line);
             font:13px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;display:none}
  .reply-meta{font-size:12px;color:var(--gold);margin-bottom:6px;font-family:ui-sans-serif,system-ui,sans-serif}
  table{width:100%;border-collapse:collapse;font-size:13px;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}
  th{text-align:left;color:var(--muted);font-weight:600;border-bottom:1px solid var(--line);
     padding:10px 12px;text-transform:uppercase;letter-spacing:.7px;font-size:11px;background:#111114}
  td{padding:10px 12px;border-bottom:1px solid #1e1e23;vertical-align:top}
  tr:last-child td{border-bottom:none}
  .mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px}
  #events{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
          padding:12px 14px;font:12px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;
          color:#c2bdb6;max-height:280px;overflow:auto;white-space:pre-wrap}
  .empty{color:var(--muted);font-style:italic}
  .guide{display:none;margin-top:14px;background:var(--panel);border:1px solid var(--gold);border-radius:var(--radius);padding:16px 18px}
  .guide.open{display:block}
  pre.code{background:#0b0b0c;border:1px solid var(--line);border-radius:7px;padding:10px 12px;overflow:auto;
           font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;color:#dcd7cf;margin:6px 0 12px}
  footer{padding:14px 28px 32px;color:#6c6862;font-size:12px;text-align:center}
</style>
</head>
<body>
<header>
  <div class="brand">
    <h1>HarnessXGate</h1>
    <span class="ver">v__VERSION__</span>
    <span class="tag">Free AI Multi-Engine Router · <span id="clock">—</span></span>
  </div>
  <div class="actions">
    <button id="btn-refresh" onclick="refresh(true)">Refresh Engines</button>
    <button onclick="toggleGuide()">Setup &amp; MCP Guide</button>
  </div>
</header>

<main>
  <div class="guide" id="guide">
    <div class="section-head" style="margin-top:0">
      <h2>Beginner Setup &amp; Connect Your AI App (MCP)</h2>
      <button onclick="toggleGuide()">Close</button>
    </div>
    <p class="tag" style="margin-top:0">HarnessXGate automatically rotates across whichever free AI engines you have installed. You only need ONE working engine to start.</p>
    <strong>1. Connect to Antigravity / Claude / Cursor / Hermes (MCP):</strong>
    <pre class="code" id="mcp-cmd">agy mcp add harnessxgate hxg mcp</pre>
    <button onclick="copyText('mcp-cmd', this)">Copy Antigravity Command</button>
    <pre class="code" id="mcp-json">{
  "mcpServers": {
    "harnessxgate": {
      "command": "hxg",
      "args": ["mcp"]
    }
  }
}</pre>
    <button onclick="copyText('mcp-json', this)">Copy MCP JSON</button>
    <p class="tag" style="margin-top:12px">Need a free engine? Install <b>OpenCode</b> (<code>curl -fsSL https://opencode.ai/install | bash</code>), <b>Ollama</b> (<code>https://ollama.com</code>), or run <code>hxg setup</code> to plug in any OpenAI-compatible free API key.</p>
  </div>

  <div class="section-head" style="margin-top:6px">
    <h2>Quick Ask (Auto-Failover Playground)</h2>
    <span class="tag" id="ask-hint">Picks the best free engine automatically · Ctrl+Enter to run</span>
  </div>
  <div class="ask-box">
    <div class="ask-row">
      <label class="tag">Task:
        <select id="ask-task">
          <option value="quick">Quick Answer (Fastest)</option>
          <option value="code" selected>Coding &amp; Debugging</option>
          <option value="deep">Deep Thinking</option>
          <option value="review">Code Review</option>
        </select>
      </label>
      <label class="tag">Engine:
        <select id="ask-engine">
          <option value="auto" selected>Auto (Recommended)</option>
          <option value="opencode">OpenCode</option>
          <option value="copilot">GitHub Copilot CLI</option>
          <option value="freellmapi">FreeLLMAPI / OpenAI API</option>
          <option value="ollama">Ollama (Offline)</option>
        </select>
      </label>
      <button class="primary" id="btn-run" onclick="runPrompt()">Run Prompt</button>
    </div>
    <textarea id="ask-prompt" placeholder="Ask anything or describe a coding task... (e.g., Write a Python function to parse CSV safely)"></textarea>
    <div class="reply-box" id="reply-box">
      <div class="reply-meta" id="reply-meta"></div>
      <div id="reply-text"></div>
    </div>
  </div>

  <div class="section-head">
    <h2>AI Engines</h2>
    <span class="tag" id="ready-count">checking…</span>
  </div>
  <div class="grid" id="engines"></div>

  <div class="section-head">
    <h2>Live Activity</h2>
    <span class="tag">Updates every 1.5s</span>
  </div>
  <div class="grid" id="activity"></div>
  <div id="active-list" style="margin-top:10px"></div>

  <div class="section-head">
    <h2>Recent Runs</h2>
  </div>
  <table>
    <thead>
      <tr><th>Run</th><th>Status</th><th>Engine / Model</th><th>Task</th><th>Time</th><th>Prompt &amp; Preview</th></tr>
    </thead>
    <tbody id="runs"></tbody>
  </table>

  <div class="section-head">
    <h2>Live Event Log</h2>
    <button onclick="clearLog()">Clear Log</button>
  </div>
  <div id="events" class="empty">loading…</div>
</main>

<footer>HarnessXGate v__VERSION__ · 100% local loopback (127.0.0.1) · Zero telemetry · MIT License</footer>

<script>
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function statusBadge(st) {
  const s = String(st || '').toLowerCase();
  if (s === 'healthy') return ['Ready', 'ok', 'on'];
  if (s === 'auth_required') return ['Login Needed', 'warn', 'warn'];
  if (s === 'not_installed') return ['Not Installed', 'muted', ''];
  return ['Offline', 'err', 'off'];
}

function toggleGuide() { $('guide').classList.toggle('open'); }

function copyText(id, btn) {
  const text = $(id).textContent;
  navigator.clipboard.writeText(text).then(() => {
    const old = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = old, 1400);
  });
}

async function get(path) {
  try { const r = await fetch(path); return await r.json(); }
  catch { return {}; }
}

async function refresh(forceHealth = false) {
  const btn = $('btn-refresh');
  if (forceHealth) { btn.disabled = true; btn.textContent = 'Checking…'; }
  const [state, health] = await Promise.all([
    get('/api/status'),
    get(forceHealth ? '/api/health?force=1' : '/api/health')
  ]);
  if (forceHealth) { btn.disabled = false; btn.textContent = 'Refresh Engines'; }
  $('clock').textContent = new Date().toLocaleTimeString();

  const engines = Object.entries(health).filter(([k]) => k !== 'error');
  const readyCount = engines.filter(([, d]) => d.status === 'healthy').length;
  $('ready-count').textContent = `${readyCount} of ${engines.length} engines ready`;
  $('engines').innerHTML = engines.length
    ? engines.map(([name, d]) => {
        const [label, bcls, dot] = statusBadge(d.status);
        const detail = [
          d.version || '',
          d.model_count ? `${d.model_count} models` : '',
          d.base_url || '',
          d.error || (d.status !== 'healthy' ? d.setup_hint : '')
        ].filter(Boolean).join(' · ');
        return `<div class="card">
          <div class="top">
            <span class="name"><span class="dot ${dot}"></span>${esc(name)}</span>
            <span class="badge ${bcls}">${esc(label)}</span>
          </div>
          <div class="meta">${esc(detail || 'Ready')}</div>
        </div>`;
      }).join('')
    : `<div class="empty">Health unavailable</div>`;

  const byEng = Object.entries(state.by_engine || {}).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'idle';
  $('activity').innerHTML = `
    <div class="card">
      <div class="name">Active Workers Now</div>
      <div class="status">${esc(state.active_count ?? 0)}</div>
      <div class="meta">${esc(byEng)}</div>
    </div>
    <div class="card">
      <div class="name">Completed Runs</div>
      <div class="status">${esc((state.recent_runs || []).length)}</div>
      <div class="meta">Stored locally in ~/.harnessxgate</div>
    </div>`;

  const active = state.active_runs || [];
  $('active-list').innerHTML = active.length
    ? `<table><thead><tr><th>Run</th><th>Engine / Model</th><th>Task</th><th>Elapsed</th><th>Working On</th></tr></thead><tbody>` +
      active.map(r => `<tr>
        <td class="mono">${esc(r.run_id)}</td>
        <td class="mono">${esc(r.engine)} / ${esc(r.model)}</td>
        <td>${esc(r.task)}</td>
        <td class="mono">${esc(r.elapsed_s)}s</td>
        <td>${esc(r.prompt_preview)}</td>
      </tr>`).join('') + `</tbody></table>`
    : '';

  const runs = state.recent_runs || [];
  $('runs').innerHTML = runs.length
    ? runs.map(r => {
        const b = r.ok ? '<span class="badge ok">OK</span>' : '<span class="badge err">FAIL</span>';
        const fo = r.failovers ? ` <span class="badge warn">${esc(r.failovers)} failover</span>` : '';
        return `<tr>
          <td class="mono">${esc(r.run_id)}</td>
          <td>${b}${fo}</td>
          <td class="mono">${esc(r.engine)}<br><span class="tag">${esc(r.model)}</span></td>
          <td>${esc(r.task)}</td>
          <td class="mono">${esc(r.elapsed_s != null ? r.elapsed_s + 's' : '—')}</td>
          <td><div>${esc(r.prompt_preview)}</div>${r.reply_preview ? `<div class="tag mono" style="margin-top:4px">${esc(r.reply_preview)}</div>` : ''}</td>
        </tr>`;
      }).join('')
    : `<tr><td colspan="6" class="empty">No runs yet — type a prompt above to test!</td></tr>`;

  const evEl = $('events');
  const events = (state.recent_events || []).slice().reverse();
  if (events.length) {
    evEl.classList.remove('empty');
    evEl.textContent = events.join('\n');
  } else {
    evEl.classList.add('empty');
    evEl.textContent = 'No events logged yet.';
  }
}

async function runPrompt() {
  const prompt = $('ask-prompt').value.trim();
  if (!prompt) return;
  const btn = $('btn-run');
  btn.disabled = true;
  btn.textContent = 'Running…';
  $('reply-box').style.display = 'block';
  $('reply-meta').textContent = 'Routing through HarnessXGate… (watch Live Activity below)';
  $('reply-text').textContent = '';
  try {
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        prompt,
        task: $('ask-task').value,
        engine: $('ask-engine').value
      })
    });
    const data = await res.json();
    if (data.ok) {
      const fo = (data.failover_from || []).length ? ` · auto-switched after ${data.failover_from.length} retry` : '';
      $('reply-meta').textContent = `Answered by ${data.engine} / ${data.model} in ${data.elapsed_s}s${fo}`;
      $('reply-text').textContent = data.text || '';
    } else {
      $('reply-meta').textContent = `All engines failed (${data.elapsed_s || 0}s) — check Setup Guide`;
      $('reply-text').textContent = JSON.stringify(data.attempts || data, null, 2);
    }
  } catch (err) {
    $('reply-meta').textContent = 'Request error';
    $('reply-text').textContent = String(err);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Run Prompt';
    refresh(false);
  }
}

async function clearLog() {
  await fetch('/api/events/clear', {method: 'POST'});
  refresh(false);
}

$('ask-prompt').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) runPrompt();
});

refresh(false);
setInterval(() => refresh(false), 1500);
</script>
</body>
</html>
""".replace("__VERSION__", __version__)


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args: Any) -> None:
        pass

    def _send(self, body: str | bytes, ctype: str, status: int = 200) -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        if path in ("/api/status", "/api/state"):
            self._send(json.dumps(router.get_fleet_status(events_limit=60), indent=2, ensure_ascii=False), "application/json")
        elif path == "/api/events":
            st = router.get_fleet_status(events_limit=120)
            self._send(json.dumps(list(reversed(st["recent_events"])), indent=2, ensure_ascii=False), "application/json")
        elif path == "/api/health":
            force = qs.get("force", ["0"])[0] == "1"
            self._send(json.dumps(get_health(force=force), indent=2, ensure_ascii=False), "application/json")
        else:
            self._send(HTML, "text/html; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/events/clear":
            router.clear_events()
            self._send('{"ok": true}', "application/json")
            return
        if path == "/api/ask":
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > MAX_POST_BYTES:
                self._send('{"ok": false, "error": "Invalid payload size"}', "application/json", status=400)
                return
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                self._send('{"ok": false, "error": "Invalid JSON"}', "application/json", status=400)
                return
            prompt = str(body.get("prompt", "")).strip()
            if not prompt:
                self._send('{"ok": false, "error": "Prompt is required"}', "application/json", status=400)
                return
            engine = str(body.get("engine", "auto"))
            task = str(body.get("task", "code"))
            if engine not in {"auto", "opencode", "copilot", "freellmapi", "ollama"}:
                engine = "auto"
            if task not in {"quick", "code", "deep", "review"}:
                task = "code"
            res = router.dispatch_ask(prompt=prompt, engine=engine, task=task, failover=True, timeout=120.0)
            self._send(json.dumps(res, ensure_ascii=False), "application/json")
            return
        self._send('{"error": "Not found"}', "application/json", status=404)


def run_server(host: str = "127.0.0.1", port: int = 7878) -> int:
    server = http.server.ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"HarnessXGate dashboard running at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_server())
