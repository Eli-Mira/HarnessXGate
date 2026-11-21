#!/usr/bin/env python3
"""Live terminal monitor for HarnessXGate (`hxg watch`)."""

from __future__ import annotations

import sys
import time

from harnessxgate import router


def render_watch(*, once: bool = False, interval: float = 1.0) -> int:
    while True:
        st = router.get_fleet_status(events_limit=12)
        if not once:
            sys.stdout.write("\x1b[2J\x1b[H")
        by_eng = ", ".join(f"{k}:{v}" for k, v in (st.get("by_engine") or {}).items()) or "none"
        lines = [
            f"=== HarnessXGate Live Monitor ({time.strftime('%H:%M:%S')}) ===",
            f"Active workers: {st['active_count']} | By engine: {by_eng}",
            "",
            "-- Active --",
        ]
        if st["active_runs"]:
            for r in st["active_runs"]:
                lines.append(f"  [{r['run_id']}] {r['engine']} / {r['model']} ({r['elapsed_s']}s) :: {r['prompt_preview']}")
        else:
            lines.append("  (idle)")
        lines.append("")
        lines.append("-- Recent Completed --")
        for r in st["recent_runs"][:5]:
            tag = "OK" if r.get("ok") else "FAIL"
            lines.append(f"  [{r['run_id']}] {tag} {r['engine']} / {r['model']} ({r['elapsed_s']}s) :: {r['prompt_preview']}")
        lines.append("")
        lines.append("-- Live Events --")
        for ev in st["recent_events"]:
            lines.append(f"  {ev}")
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        if once:
            return 0
        time.sleep(interval)
