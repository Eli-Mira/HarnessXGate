#!/usr/bin/env python3
"""Simple beginner-friendly CLI for HarnessXGate (`hxg`)."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser

from harnessxgate import __version__, dashboard, mcp_server, router, watch


def _run_setup() -> int:
    print("HarnessXGate Quick Setup (press Enter to skip any step)\n")
    cfg = router.load_user_config()
    cur_url = cfg.get("freellmapi_url", "http://127.0.0.1:3001")
    url = input(f"OpenAI-compatible / FreeLLMAPI URL [{cur_url}]: ").strip() or cur_url
    key = input("API key (leave blank to keep existing or use free CLI engines only): ").strip()
    ollama_cur = cfg.get("ollama_url", "http://127.0.0.1:11434")
    ollama_url = input(f"Ollama local URL [{ollama_cur}]: ").strip() or ollama_cur
    cfg["freellmapi_url"] = url
    cfg["ollama_url"] = ollama_url
    if key:
        cfg["freellmapi_api_key"] = key
    path = router.save_user_config(cfg)
    print(f"\nSaved config to: {path}")
    print("Checking engines...")
    h = router.check_all_health()
    for name, info in h.items():
        print(f"  - {name:10s}: {info.get('status')} ({info.get('model_count', 0)} models)")
    print("\nNext: run `hxg` to open the live dashboard in your browser!")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hxg",
        description="HarnessXGate — Free AI multi-engine router, live dashboard, and MCP server.",
    )
    p.add_argument("-v", "--version", action="version", version=f"HarnessXGate {__version__}")
    sub = p.add_subparsers(dest="command")

    ui_p = sub.add_parser("ui", help="Start the live web dashboard (default when running `hxg`)")
    ui_p.add_argument("--port", type=int, default=7878)
    ui_p.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")

    sub.add_parser("health", help="Check live status across OpenCode, Copilot, FreeLLMAPI, and Ollama")

    stat_p = sub.add_parser("status", help="Show active running workers and recent events")
    stat_p.add_argument("--limit", type=int, default=20)

    ask_p = sub.add_parser("ask", help="Send a prompt with automatic model & engine failover")
    ask_p.add_argument("prompt", nargs="+", help="Your question or task")
    ask_p.add_argument("--engine", choices=["auto", "opencode", "copilot", "freellmapi", "ollama"], default="auto")
    ask_p.add_argument("--task", choices=["quick", "code", "deep", "review"], default="code")
    ask_p.add_argument("--model", default=None)
    ask_p.add_argument("--workdir", default=".")
    ask_p.add_argument("--agentic", action="store_true")
    ask_p.add_argument("--no-failover", action="store_true")
    ask_p.add_argument("--timeout", type=float, default=120.0)
    ask_p.add_argument("--json", action="store_true", dest="as_json", help="Print full JSON telemetry")

    watch_p = sub.add_parser("watch", help="Live terminal worker monitor")
    watch_p.add_argument("--once", action="store_true")
    watch_p.add_argument("--interval", type=float, default=1.0)

    sess_p = sub.add_parser("sessions", help="List recent OpenCode and Copilot sessions")
    sess_p.add_argument("--engine", choices=["all", "opencode", "copilot"], default="all")
    sess_p.add_argument("--limit", type=int, default=10)

    sub.add_parser("mcp", help="Run stdio MCP server (for Antigravity, Claude, Cursor, Hermes)")
    sub.add_parser("setup", help="Interactive 30-second setup wizard")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cmd = args.command or "ui"

    if cmd == "ui":
        port = getattr(args, "port", 7878)
        open_browser = not getattr(args, "no_browser", False)
        if open_browser:
            webbrowser.open(f"http://127.0.0.1:{port}")
        return dashboard.run_server(port=port)

    if cmd == "health":
        rep = router.check_all_health()
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0 if any(v.get("status") == "healthy" for v in rep.values()) else 1

    if cmd == "status":
        print(json.dumps(router.get_fleet_status(events_limit=args.limit), indent=2, ensure_ascii=False))
        return 0

    if cmd == "ask":
        prompt_text = " ".join(args.prompt)
        res = router.dispatch_ask(
            prompt=prompt_text,
            engine=args.engine,
            model=args.model,
            workdir=args.workdir,
            agentic=args.agentic,
            failover=not args.no_failover,
            timeout=args.timeout,
            task=args.task,
        )
        if args.as_json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif res.get("ok"):
            print(res.get("text", ""))
            print(f"\n[{res.get('engine')} / {res.get('model')} · {res.get('elapsed_s')}s]", file=sys.stderr)
        else:
            print(json.dumps(res, indent=2, ensure_ascii=False), file=sys.stderr)
        return 0 if res.get("ok") else 1

    if cmd == "watch":
        try:
            return watch.render_watch(once=args.once, interval=args.interval)
        except KeyboardInterrupt:
            return 0

    if cmd == "sessions":
        print(json.dumps(router.list_sessions(engine=args.engine, limit=args.limit), indent=2, ensure_ascii=False))
        return 0

    if cmd == "mcp":
        return mcp_server.serve_stdio()

    if cmd == "setup":
        return _run_setup()

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
