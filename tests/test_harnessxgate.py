"""Stdlib test suite for HarnessXGate (router failover, MCP JSON-RPC, dashboard HTTP, privacy hygiene)."""

from __future__ import annotations

import io
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from harnessxgate import dashboard, mcp_server, router

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestHarnessXGate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp_path = pathlib.Path(self._tmp.name)
        self._orig_home = router.HOME_DIR
        self._orig_state = router.STATE_PATH
        self._orig_events = router.EVENTS_LOG_PATH
        self._orig_config = router.CONFIG_PATH
        router.HOME_DIR = tmp_path
        router.STATE_PATH = tmp_path / "fleet_state.json"
        router.EVENTS_LOG_PATH = tmp_path / "fleet_events.log"
        router.CONFIG_PATH = tmp_path / "config.json"

    def tearDown(self) -> None:
        router.HOME_DIR = self._orig_home
        router.STATE_PATH = self._orig_state
        router.EVENTS_LOG_PATH = self._orig_events
        router.CONFIG_PATH = self._orig_config
        self._tmp.cleanup()

    def test_auto_failover_switches_engines_and_updates_state(self) -> None:
        with (
            mock.patch.object(router, "ask_opencode", side_effect=RuntimeError("opencode CLI not found")),
            mock.patch.object(router, "ask_copilot", side_effect=RuntimeError("copilot CLI not found")),
            mock.patch.object(
                router,
                "ask_freellmapi",
                return_value={"ok": True, "engine": "freellmapi", "model": "auto:smartnfast", "text": "FALLBACK_OK"},
            ),
        ):
            res = router.dispatch_ask(prompt="hello test", engine="auto", task="quick")
            self.assertTrue(res["ok"])
            self.assertEqual(res["engine"], "freellmapi")
            self.assertEqual(res["text"], "FALLBACK_OK")
            self.assertEqual(len(res["failover_from"]), 2)

        st = router.get_fleet_status()
        self.assertEqual(st["active_count"], 0)
        self.assertEqual(len(st["recent_runs"]), 1)
        self.assertTrue(st["recent_runs"][0]["ok"])
        self.assertEqual(st["recent_runs"][0]["failovers"], 2)
        self.assertTrue(any("DONE" in e for e in st["recent_events"]))

    def test_opencode_task_ladders_have_no_fake_freemodel(self) -> None:
        for task, models in router.OPENCODE_TASK_LADDERS.items():
            self.assertTrue(models, f"Empty ladder for {task}")
            for m in models:
                self.assertFalse(m.startswith("freemodel/"), f"Fake provider found: {m}")

    def test_mcp_stdio_initialize_list_and_status(self) -> None:
        in_data = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "fleet_status", "arguments": {}}}),
        ]) + "\n"
        out_buf = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(in_data)), mock.patch("sys.stdout", out_buf):
            rc = mcp_server.serve_stdio()
        self.assertEqual(rc, 0)
        lines = [json.loads(line) for line in out_buf.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0]["result"]["serverInfo"]["name"], "harnessxgate")
        tool_names = [t["name"] for t in lines[1]["result"]["tools"]]
        self.assertEqual(tool_names, ["fleet_health", "fleet_status", "fleet_ask", "fleet_sessions"])
        self.assertFalse(lines[2]["result"]["isError"])

    def test_dashboard_endpoints_and_validation(self) -> None:
        srv = dashboard.http.server.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{port}/", timeout=3) as r:
                self.assertEqual(r.status, 200)
                html = r.read().decode("utf-8")
                self.assertIn("HarnessXGate", html)
                self.assertIn("Quick Ask", html)
            with opener.open(f"http://127.0.0.1:{port}/api/status", timeout=3) as r:
                self.assertEqual(r.status, 200)
                st = json.loads(r.read().decode("utf-8"))
                self.assertTrue(st["ok"])
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/ask",
                    data=b'{"prompt":"   "}',
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                opener.open(req, timeout=3)
            self.assertEqual(ctx.exception.code, 400)
            ctx.exception.close()
        finally:
            srv.shutdown()
            srv.server_close()

    def test_no_hardcoded_personal_identifiers(self) -> None:
        forbidden = ["emadg", "elilain_secret", "Elsebaey", "medical_dms", "hugesystem"]
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.name == "test_harnessxgate.py":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for tok in forbidden:
                self.assertNotIn(tok, text, f"Forbidden personal token {tok!r} in {path}")


if __name__ == "__main__":
    unittest.main()
