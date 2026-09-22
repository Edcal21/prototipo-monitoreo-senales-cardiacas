#!/usr/bin/env python3
"""Poll GET /system/status on the running backend and log CPU/RAM/temperature/uptime over
time. Uses the endpoint already exposed by backend_iot.py (get_system_status_payload) --
no backend code changes needed for this script. Can run ON the Pi (recommended, avoids
network-latency noise in the CPU numbers) or remotely.

Usage:
    python monitor_resources.py --host 127.0.0.1 --port 8000 --api-key devkey-123 \
        --duration-s 1800 --interval-s 2 --out results/resources.csv
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import requests


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--duration-s", type=float, default=1800.0)
    ap.add_argument("--interval-s", type=float, default=2.0)
    ap.add_argument("--out", default="results/resources.csv")
    args = ap.parse_args()

    url = f"http://{args.host}:{args.port}/system/status"
    headers = {"x-api-key": args.api_key}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "t_wall", "t_elapsed_s", "cpu_percent", "ram_percent", "ram_used_mb",
        "disk_percent", "temperature_c", "uptime_s", "clients", "quality", "error",
    ]
    t0 = time.time()
    n_errors = 0
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        deadline = time.monotonic() + args.duration_s
        next_tick = time.monotonic()
        while time.monotonic() < deadline:
            row = {"t_wall": time.time(), "t_elapsed_s": round(time.time() - t0, 1)}
            try:
                r = requests.get(url, headers=headers, timeout=5)
                r.raise_for_status()
                payload = r.json()
                row.update({
                    "cpu_percent": payload.get("cpu_percent"),
                    "ram_percent": payload.get("ram_percent"),
                    "ram_used_mb": payload.get("ram_used_mb"),
                    "disk_percent": payload.get("disk_percent"),
                    "temperature_c": payload.get("temperature_c"),
                    "uptime_s": payload.get("uptime_s"),
                    "clients": payload.get("clients"),
                    "quality": payload.get("quality"),
                    "error": "",
                })
            except Exception as exc:  # network hiccup, backend restart, etc. -- log, don't crash
                n_errors += 1
                row["error"] = f"{type(exc).__name__}: {exc}"
            writer.writerow(row)
            fh.flush()
            next_tick += args.interval_s
            sleep_s = max(0.0, next_tick - time.monotonic())
            time.sleep(sleep_s)

    print(f"Wrote {out_path} ({n_errors} request errors over the run)")


if __name__ == "__main__":
    main()
