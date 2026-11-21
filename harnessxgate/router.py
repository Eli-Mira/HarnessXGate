#!/usr/bin/env python3
"""HarnessXGate core router — zero-dependency multi-engine AI dispatcher with automatic failover.

Engines supported out of the box (auto-discovered, zero hardcoded user paths):
  1. OpenCode CLI (native on PATH or WSL daemon) — free `opencode/*` models rated by task
  2. GitHub Copilot CLI (`copilot`) — auto-model selection + agentic support
  3. FreeLLMAPI / OpenAI-compatible router (`FREELLMAPI_URL`, default http://127.0.0.1:3001)
  4. Ollama local models (`OLLAMA_HOST`, default http://127.0.0.1:11434) — 100% offline & free

SECURITY:
  - Reads API keys and local service passwords strictly in memory from env vars or `~/.harnessxgate/.env`.
  - Never logs, prints, or serializes API keys or auth credentials.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import platform
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Portable Paths & Configuration
# ---------------------------------------------------------------------------

HOME_DIR = pathlib.Path(os.environ.get("HARNESSXGATE_HOME") or (pathlib.Path.home() / ".harnessxgate"))
STATE_PATH = HOME_DIR / "fleet_state.json"
EVENTS_LOG_PATH = HOME_DIR / "fleet_events.log"
CONFIG_PATH = HOME_DIR / "config.json"
_STATE_LOCK = threading.Lock()

OPENCODE_TASK_LADDERS: dict[str, list[str]] = {
    "quick": [
        "opencode/hy4-flash-free",
        "opencode/nemotron-3.5-lightning-free",
        "opencode/mimo-v2.6-flash-free",
        "opencode/flint-40b-free",
        "opencode/tidepool-alpha-free",
        "freellmapi/auto:smartnfast",
    ],
    "code": [
        "opencode/big-pickle",
        "opencode/deepseek-v4.1-flash-free",
        "opencode/hy4-flash-free",
        "opencode/iceman-free",
        "opencode/mimo-v2.6-flash-free",
        "opencode/nemotron-3.5-super-vl-free",
        "freellmapi/auto:best-free-pool",
    ],
    "deep": [
        "opencode/deepseek-v4.1-flash-free",
        "opencode/nemotron-3.5-super-vl-free",
        "opencode/big-pickle",
        "opencode/beam-free",
        "opencode/longcat-2.5-free",
        "opencode/iceman-free",
        "freellmapi/auto:best-free-pool",
    ],
    "review": [
        "opencode/deepseek-v4.1-flash-free",
        "opencode/big-pickle",
        "opencode/nemotron-3.5-super-vl-free",
        "opencode/beam-free",
        "opencode/flint-40b-free",
        "freellmapi/auto:best-free-pool",
    ],
}

COPILOT_MODEL_FALLBACKS: list[str | None] = [None, "mai-code-2-flash", "gpt-6-luna"]
FREELLMAPI_TASK_MODELS: dict[str, str] = {
    "quick": "auto:smartnfast",
    "code": "auto:best-free-pool",
    "deep": "auto:best-free-pool",
    "review": "auto:best-free-pool",
}


def ensure_home() -> pathlib.Path:
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    return HOME_DIR


def load_user_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_user_config(cfg: dict[str, Any]) -> pathlib.Path:
    ensure_home()
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(CONFIG_PATH)
    return CONFIG_PATH


def _http_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, Any]:
    opener = _http_opener()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    resp = opener.open(req, timeout=timeout)
    raw = resp.read().decode("utf-8", errors="replace")
    return resp.status, json.loads(raw) if raw.strip() else {}


def _read_env_files() -> dict[str, str]:
    """Read optional key=value env files without ever exposing values to logs."""
    candidates = [
        HOME_DIR / ".env",
        pathlib.Path.home() / "AppData" / "Local" / "hermes" / ".env",
        pathlib.Path.home() / ".config" / "harnessxgate" / ".env",
    ]
    allowed = {"FREELLMAPI_API_KEY", "HERMES_CUSTOM_1_API_KEY", "OPENAI_API_KEY", "HARNESSXGATE_API_KEY"}
    found: dict[str, str] = {}
    for p in candidates:
        if not p.exists():
            continue
        try:
            for raw_line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k in allowed and v and k not in found:
                    found[k] = v
        except Exception:
            continue
    return found


def _get_freellmapi_url() -> str:
    cfg = load_user_config()
    return str(
        os.environ.get("FREELLMAPI_URL")
        or cfg.get("freellmapi_url")
        or "http://127.0.0.1:3001"
    ).rstrip("/")


def _get_freellmapi_key() -> str | None:
    cfg = load_user_config()
    if cfg.get("freellmapi_api_key"):
        return str(cfg["freellmapi_api_key"]).strip() or None
    keys = _read_env_files()
    for env_name in ("FREELLMAPI_API_KEY", "HARNESSXGATE_API_KEY", "HERMES_CUSTOM_1_API_KEY"):
        if keys.get(env_name):
            return keys[env_name]
    for env_name in ("FREELLMAPI_API_KEY", "HARNESSXGATE_API_KEY", "HERMES_CUSTOM_1_API_KEY"):
        val = os.environ.get(env_name, "").strip()
        if val:
            return val
    if keys.get("OPENAI_API_KEY"):
        return keys["OPENAI_API_KEY"]
    val = os.environ.get("OPENAI_API_KEY", "").strip()
    return val or None


def _get_ollama_url() -> str:
    cfg = load_user_config()
    return str(
        os.environ.get("OLLAMA_HOST")
        or cfg.get("ollama_url")
        or "http://127.0.0.1:11434"
    ).rstrip("/")


def _win_to_wsl_path(path_str: str) -> str:
    p = pathlib.Path(path_str).resolve().as_posix()
    if len(p) >= 2 and p[1] == ":":
        return f"/mnt/{p[0].lower()}{p[2:]}"
    return p


def _resolve_copilot_bin() -> str | None:
    found = shutil.which("copilot")
    if found:
        return found
    home = pathlib.Path.home()
    candidates = [
        home / "AppData" / "Local" / "Programs" / "Microsoft VS Code" / "bin" / "copilot-shim" / "copilot.exe",
        home / "AppData" / "Roaming" / "npm" / "copilot.cmd",
        home / ".local" / "bin" / "copilot",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _detect_wsl_opencode() -> tuple[str | None, str | None, str | None]:
    """On Windows, detect (wsl_distro, opencode_bin_path, service_url) if WSL OpenCode is installed."""
    if platform.system() != "Windows" or not shutil.which("wsl"):
        return None, None, None
    cfg = load_user_config()
    distro = str(os.environ.get("HARNESSXGATE_WSL_DISTRO") or cfg.get("wsl_distro") or "").strip()
    distros = [distro] if distro else ["Debian", "Ubuntu"]
    for d in distros:
        try:
            proc = subprocess.run(
                ["wsl", "-d", d, "--", "sh", "-lc", 'command -v opencode || [ -x "$HOME/.opencode/bin/opencode" ] && echo "$HOME/.opencode/bin/opencode"'],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=4.0,
            )
            bin_path = (proc.stdout or "").strip().splitlines()
            if proc.returncode == 0 and bin_path and bin_path[0].startswith("/"):
                svc = subprocess.run(
                    ["wsl", "-d", d, "--", bin_path[0], "service", "status"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=4.0,
                )
                url = (svc.stdout or "").strip().splitlines()
                svc_url = url[0].strip() if svc.returncode == 0 and url and url[0].startswith("http") else None
                return d, bin_path[0].strip(), svc_url
        except Exception:
            continue
    return None, None, None


def _resolve_opencode_runtime() -> dict[str, Any]:
    """Resolve native OpenCode binary first, then WSL OpenCode on Windows."""
    cfg = load_user_config()
    url_override = str(os.environ.get("OPENCODE_URL") or cfg.get("opencode_url") or "").strip()
    native = shutil.which("opencode")
    if not native:
        local_bin = pathlib.Path.home() / ".opencode" / "bin" / ("opencode.exe" if platform.system() == "Windows" else "opencode")
        if local_bin.exists():
            native = str(local_bin)

    # Prefer WSL OpenCode on Windows if its daemon is actively running; otherwise native.
    if platform.system() == "Windows":
        distro, wsl_bin, wsl_url = _detect_wsl_opencode()
        if distro and wsl_bin and wsl_url:
            return {"mode": "wsl", "distro": distro, "bin": wsl_bin, "url": url_override or wsl_url}
        if native:
            return {"mode": "native", "bin": native, "url": url_override or "http://127.0.0.1:49374"}
        if distro and wsl_bin:
            return {"mode": "wsl", "distro": distro, "bin": wsl_bin, "url": url_override or "http://127.0.0.1:49374"}
        return {"mode": "none", "bin": None, "url": None}

    if native:
        return {"mode": "native", "bin": native, "url": url_override or "http://127.0.0.1:49374"}
    return {"mode": "none", "bin": None, "url": None}


def _get_opencode_service_auth(rt: dict[str, Any]) -> str | None:
    candidates: list[pathlib.Path] = [pathlib.Path.home() / ".config" / "opencode" / "service.json"]
    if rt.get("mode") == "wsl" and rt.get("distro"):
        try:
            proc = subprocess.run(
                ["wsl", "-d", rt["distro"], "--", "sh", "-lc", 'cat "$HOME/.config/opencode/service.json" 2>/dev/null'],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                pwd = str(json.loads(proc.stdout).get("password", "")).strip()
                if pwd:
                    return "Basic " + base64.b64encode(f"opencode:{pwd}".encode("utf-8")).decode("ascii")
        except Exception:
            pass
    for p in candidates:
        if not p.exists():
            continue
        try:
            pwd = str(json.loads(p.read_text(encoding="utf-8", errors="replace")).get("password", "")).strip()
            if pwd:
                return "Basic " + base64.b64encode(f"opencode:{pwd}".encode("utf-8")).decode("ascii")
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Live State Registry & Event Log
# ---------------------------------------------------------------------------

def _emit_event(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        ensure_home()
        with _STATE_LOCK:
            with EVENTS_LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception:
        pass
    try:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _update_run_state(run_id: str, entry: dict[str, Any] | None, *, finish: dict[str, Any] | None = None) -> None:
    ensure_home()
    with _STATE_LOCK:
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
        except Exception:
            state = {}
        active = state.get("active") if isinstance(state.get("active"), dict) else {}
        recent = state.get("recent") if isinstance(state.get("recent"), list) else []
        if entry is not None:
            active[run_id] = entry
        if finish is not None:
            active.pop(run_id, None)
            recent.insert(0, finish)
            recent = recent[:30]
        by_engine: dict[str, int] = {}
        for item in active.values():
            eng = str(item.get("engine", "unknown"))
            by_engine[eng] = by_engine.get(eng, 0) + 1
        new_state = {"active_count": len(active), "by_engine": by_engine, "active": active, "recent": recent}
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(new_state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE_PATH)


def get_fleet_status(events_limit: int = 30) -> dict[str, Any]:
    with _STATE_LOCK:
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
        except Exception:
            state = {}
        events: list[str] = []
        if EVENTS_LOG_PATH.exists():
            events = EVENTS_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-events_limit:]
    now = time.time()
    active_dict = state.get("active") if isinstance(state.get("active"), dict) else {}
    active_list = []
    for rid, item in active_dict.items():
        rec = dict(item)
        rec["run_id"] = rid
        rec["elapsed_s"] = round(max(0.0, now - float(rec.get("started_ts", now))), 1)
        active_list.append(rec)
    return {
        "ok": True,
        "active_count": len(active_list),
        "by_engine": state.get("by_engine", {}),
        "active_runs": active_list,
        "recent_runs": (state.get("recent") or [])[:20],
        "recent_events": events,
    }


def clear_events() -> None:
    with _STATE_LOCK:
        ensure_home()
        EVENTS_LOG_PATH.write_text("", encoding="utf-8")


# ---------------------------------------------------------------------------
# Engine Health Checks
# ---------------------------------------------------------------------------

def check_opencode_health() -> dict[str, Any]:
    rt = _resolve_opencode_runtime()
    result: dict[str, Any] = {
        "engine": "opencode",
        "status": "not_installed",
        "mode": rt["mode"],
        "base_url": rt["url"],
        "version": None,
        "model_count": 0,
        "setup_hint": "Install free OpenCode CLI: curl -fsSL https://opencode.ai/install | bash",
    }
    if rt["mode"] == "none" or not rt["bin"]:
        return result

    try:
        cmd = (
            ["wsl", "-d", rt["distro"], "--", rt["bin"], "--version"]
            if rt["mode"] == "wsl"
            else [rt["bin"], "--version"]
        )
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=6.0)
        ver = (proc.stdout or proc.stderr or "").strip().splitlines()
        result["version"] = ver[0].strip() if ver else None
        result["status"] = "healthy" if proc.returncode == 0 else "down"
        result["model_count"] = len(OPENCODE_TASK_LADDERS["code"])
    except Exception as exc:
        result["status"] = "down"
        result["error"] = str(exc)
        return result

    auth_hdr = _get_opencode_service_auth(rt)
    if auth_hdr and rt.get("url"):
        try:
            st, data = _http_json(
                f"{rt['url']}/api/provider",
                headers={"Authorization": auth_hdr, "Accept": "application/json"},
                timeout=3.0,
            )
            if st == 200 and isinstance(data, dict):
                provs = data.get("data", data)
                if isinstance(provs, list):
                    result["providers"] = [p.get("id") for p in provs if isinstance(p, dict) and p.get("id")]
        except Exception:
            pass
    return result


def check_copilot_health() -> dict[str, Any]:
    bin_path = _resolve_copilot_bin()
    cfg_path = pathlib.Path.home() / ".copilot" / "config.json"
    result: dict[str, Any] = {
        "engine": "copilot",
        "status": "not_installed",
        "binary": bin_path,
        "version": None,
        "auth_configured": False,
        "setup_hint": "Install GitHub Copilot CLI & run: copilot login",
    }
    if not bin_path:
        return result
    if cfg_path.exists():
        try:
            raw = cfg_path.read_text(encoding="utf-8", errors="replace")
            result["auth_configured"] = ("loggedInUsers" in raw or "logged_in_users" in raw) and "login" in raw
        except Exception:
            pass
    try:
        proc = subprocess.run([bin_path, "--version"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=6.0)
        ver = (proc.stdout or proc.stderr or "").strip().splitlines()
        result["version"] = ver[0].strip() if ver else None
        if proc.returncode == 0:
            result["status"] = "healthy" if result["auth_configured"] else "auth_required"
            if not result["auth_configured"]:
                result["error"] = "Run `copilot login` to authenticate"
        else:
            result["status"] = "down"
    except Exception as exc:
        result["status"] = "down"
        result["error"] = str(exc)
    return result


def check_freellmapi_health() -> dict[str, Any]:
    base_url = _get_freellmapi_url()
    key = _get_freellmapi_key()
    result: dict[str, Any] = {
        "engine": "freellmapi",
        "base_url": base_url,
        "status": "down",
        "key_configured": bool(key),
        "model_count": 0,
        "setup_hint": "Set FREELLMAPI_URL + FREELLMAPI_API_KEY via `hxg setup` (works with FreeLLMAPI, OpenRouter, Groq, etc.)",
    }
    try:
        st, livez = _http_json(f"{base_url}/livez", timeout=2.5)
        if st == 200:
            result["livez"] = livez
            result["status"] = "healthy"
    except Exception:
        pass
    if key:
        try:
            st, models = _http_json(
                f"{base_url}/v1/models",
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
                timeout=4.0,
            )
            if st == 200 and isinstance(models, dict):
                rows = models.get("data", [])
                result["model_count"] = len(rows) if isinstance(rows, list) else 0
                result["status"] = "healthy"
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                result["status"] = "auth_required"
                result["error"] = f"API key rejected (HTTP {exc.code}) — update via `hxg setup`"
            elif result["status"] != "healthy":
                result["error"] = str(exc)
        except Exception as exc:
            if result["status"] != "healthy":
                result["error"] = str(exc)
    elif result["status"] == "healthy":
        result["status"] = "auth_required"
        result["error"] = "Missing FREELLMAPI_API_KEY (run `hxg setup`)"
    return result


def check_ollama_health() -> dict[str, Any]:
    base_url = _get_ollama_url()
    result: dict[str, Any] = {
        "engine": "ollama",
        "base_url": base_url,
        "status": "down",
        "model_count": 0,
        "models": [],
        "setup_hint": "Optional 100% offline AI: install Ollama (https://ollama.com) & run `ollama pull qwen2.5-coder`",
    }
    try:
        st, data = _http_json(f"{base_url}/api/tags", timeout=2.0)
        if st == 200 and isinstance(data, dict):
            models = [m.get("name") for m in data.get("models", []) if isinstance(m, dict) and m.get("name")]
            result["models"] = models
            result["model_count"] = len(models)
            result["status"] = "healthy" if models else "down"
            if not models:
                result["error"] = "Ollama running, no models pulled yet (run `ollama pull qwen2.5-coder`)"
    except Exception:
        pass
    return result


def check_all_health() -> dict[str, Any]:
    return {
        "opencode": check_opencode_health(),
        "copilot": check_copilot_health(),
        "freellmapi": check_freellmapi_health(),
        "ollama": check_ollama_health(),
    }


# ---------------------------------------------------------------------------
# Engine Execution (`ask`)
# ---------------------------------------------------------------------------

def ask_opencode(prompt: str, model: str | None, workdir: str, timeout: float = 120.0) -> dict[str, Any]:
    rt = _resolve_opencode_runtime()
    if rt["mode"] == "none" or not rt["bin"]:
        raise RuntimeError("opencode CLI not found")
    chosen_model = model or "opencode/big-pickle"
    if "/" not in chosen_model:
        chosen_model = f"opencode/{chosen_model}"

    if rt["mode"] == "wsl":
        workdir_wsl = _win_to_wsl_path(workdir)
        cmd = [
            "wsl", "-d", rt["distro"], "--cd", workdir_wsl, "-e",
            "timeout", "--signal=TERM", "--kill-after=5s", f"{int(timeout)}s",
            rt["bin"], "run", "--model", chosen_model, "--auto", "--format", "json", "--archived", prompt,
        ]
    else:
        cmd = [rt["bin"], "run", "--model", chosen_model, "--auto", "--format", "json", "--archived", prompt]

    proc = subprocess.run(
        cmd,
        cwd=None if rt["mode"] == "wsl" else str(workdir),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout + 15,
    )
    text_parts: list[str] = []
    session_id: str | None = None
    tokens: dict[str, Any] = {}
    cost = 0
    errors: list[str] = []
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_id = ev.get("sessionID") or session_id
        ev_type = ev.get("type")
        part = ev.get("part") or {}
        if ev_type == "text" and isinstance(part.get("text"), str):
            text_parts.append(part["text"])
        elif ev_type == "step_finish":
            tokens = part.get("tokens") or tokens
            cost = part.get("cost", cost)
        elif ev_type == "error":
            errors.append(json.dumps(ev.get("error") or ev))

    text = "".join(text_parts).strip()
    if proc.returncode != 0 or errors or not text:
        err = "; ".join(errors) or proc.stderr.strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"opencode run failed: {err[:300]}")
    return {
        "ok": True,
        "engine": "opencode",
        "model": chosen_model,
        "session_id": session_id,
        "cost": cost,
        "tokens": tokens,
        "text": text,
    }


def ask_copilot(
    prompt: str, model: str | None, workdir: str, *, agentic: bool = False, timeout: float = 120.0
) -> dict[str, Any]:
    bin_path = _resolve_copilot_bin()
    if not bin_path:
        raise RuntimeError("copilot CLI not found")
    cmd = [
        bin_path, "-p", prompt, "--output-format", "json",
        "--no-auto-update", "--no-color", "--no-ask-user", "-C", str(workdir),
    ]
    if model:
        cmd.extend(["--model", model])
    if agentic:
        cmd.append("--allow-all")
    else:
        cmd.extend(["--disable-builtin-mcps", "--no-custom-instructions"])

    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout + 15)
    session_id: str | None = None
    resolved_model: str | None = None
    final_texts: list[str] = []
    all_texts: list[str] = []
    errors: list[str] = []
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        ev_type = ev.get("type")
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        if ev_type == "session.start":
            session_id = data.get("sessionId") or session_id
        elif ev_type == "session.auto_mode_resolved":
            resolved_model = data.get("chosenModel") or resolved_model
        elif ev_type == "assistant.message":
            resolved_model = data.get("model") or resolved_model
            content = data.get("content")
            if isinstance(content, str) and content.strip():
                all_texts.append(content.strip())
                if data.get("phase") == "final_answer":
                    final_texts.append(content.strip())
        elif ev_type == "error":
            errors.append(str(data.get("message") or ev))

    text = "\n".join(final_texts) if final_texts else (all_texts[-1] if all_texts else "")
    if proc.returncode != 0 or errors or not text:
        err = "; ".join(errors) or proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"copilot CLI failed: {err[:300]}")
    return {
        "ok": True,
        "engine": "copilot",
        "mode": "agentic" if agentic else "non-interactive",
        "model": resolved_model or model or "auto",
        "session_id": session_id,
        "text": text,
    }


def ask_freellmapi(prompt: str, model: str | None, timeout: float = 90.0, task: str = "code") -> dict[str, Any]:
    key = _get_freellmapi_key()
    if not key:
        raise RuntimeError("missing apiKey for FreeLLMAPI / OpenAI-compatible endpoint (run `hxg setup`)")
    base_url = _get_freellmapi_url()
    chosen_model = (model or FREELLMAPI_TASK_MODELS.get(task, "auto:smartnfast")).removeprefix("freellmapi/")
    status, data = _http_json(
        f"{base_url}/v1/chat/completions",
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"},
        payload={"model": chosen_model, "messages": [{"role": "user", "content": prompt}], "stream": False},
        timeout=timeout,
    )
    choices = data.get("choices") or []
    msg = choices[0].get("message", {}) if choices else {}
    content = msg.get("content") or msg.get("reasoning_content") or ""
    if status != 200 or not content:
        raise RuntimeError(f"FreeLLMAPI returned HTTP {status} with empty content")
    return {
        "ok": True,
        "engine": "freellmapi",
        "model": data.get("model", chosen_model),
        "text": content,
        "usage": data.get("usage", {}),
    }


def ask_ollama(prompt: str, model: str | None, timeout: float = 120.0) -> dict[str, Any]:
    health = check_ollama_health()
    if health.get("status") != "healthy" or not health.get("models"):
        raise RuntimeError("ollama unreachable or no models installed")
    chosen = model or health["models"][0]
    base_url = _get_ollama_url()
    status, data = _http_json(
        f"{base_url}/v1/chat/completions",
        method="POST",
        headers={"Content-Type": "application/json"},
        payload={"model": chosen, "messages": [{"role": "user", "content": prompt}], "stream": False},
        timeout=timeout,
    )
    choices = data.get("choices") or []
    content = (choices[0].get("message", {}) if choices else {}).get("content") or ""
    if status != 200 or not content:
        raise RuntimeError(f"Ollama returned HTTP {status} with empty content")
    return {"ok": True, "engine": "ollama", "model": chosen, "text": content}


def _models_for_engine(eng: str, requested_model: str | None, failover: bool, task: str = "code") -> list[str | None]:
    if not failover:
        return [requested_model]
    if eng == "opencode":
        ladder: list[str | None] = list(OPENCODE_TASK_LADDERS.get(task, OPENCODE_TASK_LADDERS["code"]))
    elif eng == "copilot":
        ladder = list(COPILOT_MODEL_FALLBACKS)
    else:
        return [requested_model]
    out: list[str | None] = [requested_model] if requested_model else []
    for c in ladder:
        if c not in out:
            out.append(c)
    return out


def dispatch_ask(
    *,
    prompt: str,
    engine: str = "auto",
    model: str | None = None,
    workdir: str = ".",
    agentic: bool = False,
    failover: bool = True,
    timeout: float = 120.0,
    task: str = "code",
) -> dict[str, Any]:
    attempts: list[dict[str, str]] = []
    run_id = uuid.uuid4().hex[:8]
    started_ts = time.time()
    preview = " ".join(prompt.strip().split())[:100]

    if engine == "auto":
        order = ["opencode", "copilot", "freellmapi", "ollama"]
    else:
        order = [engine]
        if failover:
            for fb in ("freellmapi", "ollama"):
                if fb not in order:
                    order.append(fb)

    _emit_event(f"[{run_id}] START task={task} engine={engine} agentic={agentic} :: {preview}")
    for idx, eng in enumerate(order):
        req_model = model if idx == 0 else None
        for use_model in _models_for_engine(eng, req_model, failover, task=task):
            model_label = str(use_model or "default")
            _update_run_state(
                run_id,
                {
                    "engine": eng,
                    "model": model_label,
                    "task": task,
                    "agentic": agentic,
                    "workdir": str(workdir),
                    "started_ts": started_ts,
                    "status": "running",
                    "prompt_preview": preview,
                },
            )
            _emit_event(f"[{run_id}] TRY engine={eng} model={model_label}")
            try:
                if eng == "opencode":
                    res = ask_opencode(prompt, use_model, workdir, timeout=timeout)
                elif eng == "copilot":
                    res = ask_copilot(prompt, use_model, workdir, agentic=agentic, timeout=timeout)
                elif eng == "freellmapi":
                    res = ask_freellmapi(prompt, use_model, timeout=timeout, task=task)
                elif eng == "ollama":
                    res = ask_ollama(prompt, use_model, timeout=timeout)
                else:
                    raise ValueError(f"Unsupported engine: {eng}")
                elapsed = round(time.time() - started_ts, 2)
                res["run_id"] = run_id
                res["elapsed_s"] = elapsed
                if attempts:
                    res["failover_from"] = attempts
                _update_run_state(
                    run_id,
                    None,
                    finish={
                        "run_id": run_id,
                        "ok": True,
                        "engine": res.get("engine", eng),
                        "model": res.get("model", model_label),
                        "task": task,
                        "elapsed_s": elapsed,
                        "failovers": len(attempts),
                        "prompt_preview": preview,
                        "reply_preview": str(res.get("text", ""))[:240],
                    },
                )
                _emit_event(f"[{run_id}] DONE engine={res.get('engine', eng)} model={res.get('model', model_label)} elapsed={elapsed}s")
                return res
            except Exception as exc:
                err_str = str(exc)
                attempts.append({"engine": eng, "model": model_label, "error": err_str})
                _emit_event(f"[{run_id}] FAILOVER engine={eng} model={model_label} err={err_str[:120]}")
                if any(tok in err_str.lower() for tok in ("unreachable", "missing apikey", "not found", "connection refused")):
                    break

    elapsed = round(time.time() - started_ts, 2)
    _update_run_state(
        run_id,
        None,
        finish={
            "run_id": run_id,
            "ok": False,
            "engine": engine,
            "model": model or "auto",
            "task": task,
            "elapsed_s": elapsed,
            "failovers": len(attempts),
            "prompt_preview": preview,
            "reply_preview": attempts[-1]["error"][:240] if attempts else "All engines failed",
        },
    )
    _emit_event(f"[{run_id}] ERROR engine={engine} elapsed={elapsed}s")
    return {"ok": False, "run_id": run_id, "elapsed_s": elapsed, "engine": engine, "attempts": attempts}


# ---------------------------------------------------------------------------
# Sessions Inspection
# ---------------------------------------------------------------------------

def list_sessions(engine: str = "all", limit: int = 10) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if engine in ("all", "opencode"):
        rt = _resolve_opencode_runtime()
        auth_hdr = _get_opencode_service_auth(rt)
        if auth_hdr and rt.get("url"):
            try:
                _, data = _http_json(
                    f"{rt['url']}/api/session?limit={limit}",
                    headers={"Authorization": auth_hdr, "Accept": "application/json"},
                    timeout=4.0,
                )
                rows = data.get("data", []) if isinstance(data, dict) else []
                out["opencode"] = {
                    "ok": True,
                    "sessions": [
                        {"id": r.get("id"), "title": r.get("title"), "outcome": r.get("outcome")}
                        for r in rows[:limit]
                    ],
                }
            except Exception as exc:
                out["opencode"] = {"ok": False, "error": str(exc)}
        else:
            out["opencode"] = {"ok": False, "error": "OpenCode daemon unavailable"}

    if engine in ("all", "copilot"):
        db_path = pathlib.Path.home() / ".copilot" / "session-store.db"
        if db_path.exists():
            try:
                con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                con.row_factory = sqlite3.Row
                try:
                    rows = con.execute(
                        "SELECT id, cwd, summary, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                    out["copilot"] = {"ok": True, "sessions": [dict(r) for r in rows]}
                finally:
                    con.close()
            except Exception as exc:
                out["copilot"] = {"ok": False, "error": str(exc)}
        else:
            out["copilot"] = {"ok": False, "error": "Copilot session DB not found"}
    return out
