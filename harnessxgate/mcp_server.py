#!/usr/bin/env python3
"""Zero-dependency MCP stdio server for HarnessXGate (works with Antigravity, Claude, Cursor, Hermes)."""

from __future__ import annotations

import json
import sys
from typing import Any

from harnessxgate import __version__, router

PROTOCOL_VERSION = "2024-11-05"
TOOLS: list[dict[str, Any]] = [
    {
        "name": "fleet_health",
        "description": "Check live health, setup hints, and model counts across OpenCode, Copilot CLI, FreeLLMAPI, and Ollama.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "fleet_status",
        "description": "Show live active workers, count per engine, elapsed time, and recent progress events.",
        "inputSchema": {
            "type": "object",
            "properties": {"events_limit": {"type": "integer", "default": 20}},
            "additionalProperties": False,
        },
    },
    {
        "name": "fleet_ask",
        "description": "Run a prompt or coding task through HarnessXGate with automatic model & engine failover (OpenCode -> Copilot -> FreeLLMAPI -> Ollama).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Task or question text."},
                "engine": {
                    "type": "string",
                    "enum": ["auto", "opencode", "copilot", "freellmapi", "ollama"],
                    "default": "auto",
                },
                "task": {
                    "type": "string",
                    "enum": ["quick", "code", "deep", "review"],
                    "default": "code",
                },
                "model": {"type": "string", "description": "Optional explicit model ID."},
                "workdir": {"type": "string", "default": "."},
                "agentic": {"type": "boolean", "default": False},
                "timeout": {"type": "number", "default": 120.0},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "fleet_sessions",
        "description": "List recent OpenCode and Copilot CLI sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "engine": {"type": "string", "enum": ["all", "opencode", "copilot"], "default": "all"},
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
]


def handle_tool_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "fleet_health":
        return router.check_all_health()
    if name == "fleet_status":
        return router.get_fleet_status(events_limit=int(args.get("events_limit", 20)))
    if name == "fleet_ask":
        return router.dispatch_ask(
            prompt=str(args["prompt"]),
            engine=str(args.get("engine", "auto")),
            model=args.get("model"),
            workdir=str(args.get("workdir", ".")),
            agentic=bool(args.get("agentic", False)),
            failover=True,
            timeout=float(args.get("timeout", 120.0)),
            task=str(args.get("task", "code")),
        )
    if name == "fleet_sessions":
        return router.list_sessions(engine=str(args.get("engine", "all")), limit=int(args.get("limit", 10)))
    raise ValueError(f"Unknown tool: {name}")


def _write(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def serve_stdio() -> int:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as exc:
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}})
            continue
        msg_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}
        if method == "notifications/initialized" or msg_id is None:
            continue
        try:
            if method == "initialize":
                _write({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "harnessxgate", "version": __version__},
                    },
                })
            elif method == "tools/list":
                _write({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
            elif method == "tools/call":
                data = handle_tool_call(str(params.get("name", "")), params.get("arguments") or {})
                _write({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(data, indent=2, ensure_ascii=False)}],
                        "isError": data.get("ok") is False,
                    },
                })
            elif method == "ping":
                _write({"jsonrpc": "2.0", "id": msg_id, "result": {}})
            else:
                _write({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})
        except Exception as exc:
            _write({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": str(exc)}})
    return 0


if __name__ == "__main__":
    raise SystemExit(serve_stdio())
