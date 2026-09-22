#!/usr/bin/env python3
"""WebSocket latency / jitter / packet-loss / reconnection tester for /ws/ecg.

Run this from a SEPARATE machine on the same network as the Raspberry Pi (a laptop),
not on the Pi itself -- it measures what a real client experiences.

Records one CSV row per received message with:
  client_recv_monotonic, client_recv_wall, seq, server_sent_at, sample_acquired_at,
  n_samples, connection_id

From these, fs_jitter_report.py / analyze_all.py compute: inter-arrival jitter (no clock
sync needed), sequence gaps within a connection (missed/delayed ticks), reconnection count
and reconnection latency, and message-to-client latency IF the two machines' clocks are
synced (report this cautiously -- see RUNBOOK.md).

Usage:
    python ws_latency_client.py --host 192.168.4.1 --port 8000 --api-key devkey-123 \
        --duration-s 1800 --out ws_latency.csv --reconnect-every-s 300
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time
from pathlib import Path

import websockets


async def run(args: argparse.Namespace) -> None:
    url = f"ws://{args.host}:{args.port}/ws/ecg?api_key={args.api_key}"
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fh = out_path.open("w", newline="", encoding="utf-8")
    writer = csv.writer(fh)
    writer.writerow([
        "connection_id", "client_recv_monotonic", "client_recv_wall", "seq",
        "server_sent_at", "sample_acquired_at", "n_samples",
    ])

    t_deadline = time.monotonic() + args.duration_s
    connection_id = 0
    reconnects: list[dict] = []
    n_messages = 0
    n_disconnects = 0

    print(f"Connecting to {url}")
    while time.monotonic() < t_deadline:
        connection_id += 1
        connect_started = time.monotonic()
        try:
            async with websockets.connect(url, open_timeout=10, close_timeout=5) as ws:
                connected_at = time.monotonic()
                if connection_id > 1:
                    reconnects.append({
                        "connection_id": connection_id,
                        "reconnect_latency_s": round(connected_at - connect_started, 3),
                    })
                    print(f"  reconnected (id={connection_id}) after "
                          f"{connected_at - connect_started:.2f}s")
                last_forced_reconnect = time.monotonic()
                while time.monotonic() < t_deadline:
                    if args.reconnect_every_s and (
                        time.monotonic() - last_forced_reconnect >= args.reconnect_every_s
                    ):
                        print(f"  [reconnect test] forcing close at connection {connection_id}")
                        break
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=15)
                    except asyncio.TimeoutError:
                        print("  no message for 15s, treating as stalled connection")
                        break
                    recv_mono = time.monotonic()
                    recv_wall = time.time()
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    samples = msg.get("samples") or {}
                    writer.writerow([
                        connection_id, f"{recv_mono:.6f}", f"{recv_wall:.6f}",
                        msg.get("seq"), msg.get("server_sent_at"), msg.get("sample_acquired_at"),
                        len(samples.get("t") or []),
                    ])
                    n_messages += 1
                    if n_messages % 100 == 0:
                        fh.flush()
                        print(f"  {n_messages} messages, "
                              f"{t_deadline - time.monotonic():.0f}s remaining")
        except (websockets.exceptions.ConnectionClosed, OSError, asyncio.TimeoutError) as exc:
            n_disconnects += 1
            print(f"  disconnected ({type(exc).__name__}: {exc}); retrying in 2s")
            await asyncio.sleep(2)

    fh.close()
    summary = {
        "total_messages": n_messages,
        "total_connections": connection_id,
        "unplanned_disconnects": n_disconnects,
        "reconnects": reconnects,
        "duration_s": args.duration_s,
        "csv_path": str(out_path),
    }
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_path} and {summary_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True, help="Raspberry Pi IP/hostname, e.g. 192.168.4.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--duration-s", type=float, default=1800.0, help="Total test duration (default 30 min)")
    ap.add_argument("--reconnect-every-s", type=float, default=0.0,
                     help="If >0, deliberately force-close and reconnect on this interval to test reconnection behavior")
    ap.add_argument("--out", default="results/ws_latency.csv")
    args = ap.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
