#!/usr/bin/env python3
"""Combine fs_jitter_report.json, ws_latency*.csv, resources.csv, and twave_check.json
into one Markdown report answering the 5-point deployment gate in backend/MAD_INTEGRATION.md.

Usage:
    python analyze_all.py --results-dir results --out results/PI_VALIDATION_REPORT.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def section_fs_jitter(results_dir: Path) -> str:
    p = results_dir / "fs_jitter_report.json"
    if not p.exists():
        return "## 1-2. Effective sampling rate & jitter\n\n**Not run** (missing fs_jitter_report.json).\n"
    r = json.loads(p.read_text())
    return (
        "## 1-2. Effective sampling rate & jitter\n\n"
        f"- Configured: {r['configured_rate_hz']} Hz. Measured effective: "
        f"**{r['effective_fs_mean_hz']} Hz mean / {r['effective_fs_median_hz']} Hz median** "
        f"({r['effective_fs_vs_configured_pct']}% of configured), over {r['n_samples']} samples, "
        f"{r['duration_s']:.0f} s.\n"
        f"- Inter-sample interval: mean {r['dt_ms']['mean']} ms, SD (jitter) "
        f"**{r['jitter_sd_ms']} ms**, p95 {r['dt_ms']['p95']} ms, p99 {r['dt_ms']['p99']} ms, "
        f"max {r['dt_ms']['max']} ms.\n"
        f"- Stalls/gaps (> {r['gaps']['threshold_ms']} ms): **{r['gaps']['count']}**, "
        f"totaling {r['gaps']['total_stalled_time_s']} s, an estimated "
        f"**{r['gaps']['estimated_dropped_samples']} dropped samples**, worst single gap "
        f"{r['gaps']['worst_gap_ms']} ms.\n"
    )


def section_latency(results_dir: Path) -> str:
    csvs = sorted(results_dir.glob("ws_latency*.csv"))
    if not csvs:
        return "## 3. WebSocket latency, jitter, packet loss, reconnection\n\n**Not run**.\n"
    out = ["## 3. WebSocket latency, jitter, packet loss, reconnection\n"]
    for csv_path in csvs:
        df = pd.read_csv(csv_path)
        if df.empty:
            continue
        inter = df["client_recv_monotonic"].diff().dropna() * 1000.0
        n_conn = df["connection_id"].nunique()
        seq_gaps = 0
        for _, g in df.groupby("connection_id"):
            d = g["seq"].diff().dropna()
            seq_gaps += int((d > 1).sum())
        summary_path = csv_path.with_suffix(".summary.json")
        summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
        out.append(f"### {csv_path.name}\n")
        out.append(
            f"- {len(df)} messages, {n_conn} connection(s), "
            f"{summary.get('unplanned_disconnects', 'n/a')} unplanned disconnects, "
            f"{len(summary.get('reconnects', []))} reconnects logged.\n"
            f"- Inter-arrival: mean {inter.mean():.1f} ms, SD (jitter) {inter.std():.1f} ms, "
            f"p95 {inter.quantile(0.95):.1f} ms, p99 {inter.quantile(0.99):.1f} ms.\n"
            f"- Sequence gaps within a connection (missed/delayed ticks): {seq_gaps}.\n"
        )
        if df["server_sent_at"].notna().any():
            lat = (df["client_recv_wall"] - df["server_sent_at"]).dropna() * 1000.0
            out.append(
                f"- Server-send-to-client-receive latency (**requires clock-synced machines, "
                f"verify NTP on both before trusting this**): mean {lat.mean():.1f} ms, "
                f"p95 {lat.quantile(0.95):.1f} ms, p99 {lat.quantile(0.99):.1f} ms.\n"
            )
        if summary.get("reconnects"):
            rl = [r["reconnect_latency_s"] for r in summary["reconnects"]]
            out.append(f"- Reconnection latency: mean {np.mean(rl):.2f} s, max {np.max(rl):.2f} s.\n")
    return "\n".join(out)


def section_resources(results_dir: Path) -> str:
    p = results_dir / "resources.csv"
    if not p.exists():
        return "## 4. CPU, memory, temperature\n\n**Not run**.\n"
    df = pd.read_csv(p)
    ok = df[df["error"].fillna("") == ""]
    lines = [
        "## 4. CPU, memory, temperature over the session\n",
        f"- {len(df)} samples over {df['t_elapsed_s'].max():.0f} s "
        f"({len(df) - len(ok)} polling errors).\n",
        f"- CPU%: mean {ok['cpu_percent'].mean():.1f}, max {ok['cpu_percent'].max():.1f}.\n",
        f"- RAM%: mean {ok['ram_percent'].mean():.1f}, max {ok['ram_percent'].max():.1f} "
        f"({ok['ram_used_mb'].max():.0f} MB peak).\n",
    ]
    if ok["temperature_c"].notna().any():
        lines.append(
            f"- CPU temperature: mean {ok['temperature_c'].mean():.1f} C, "
            f"max {ok['temperature_c'].max():.1f} C "
            f"({'possible throttling risk, check for >80C' if ok['temperature_c'].max() > 80 else 'no throttling risk observed'}).\n"
        )
    return "\n".join(lines)


def section_twave(results_dir: Path) -> str:
    p = results_dir / "twave_check.json"
    if not p.exists():
        return "## 5. T-wave double-detection mode\n\n**Not run**.\n"
    r = json.loads(p.read_text())
    return (
        "## 5. T-wave double-detection mode (record-113-style)\n\n"
        f"- Session: {r['input']}, {r['duration_s']:.0f} s, {r['raw_peaks']} raw candidates.\n"
        f"- {r['pct_raw_peaks_in_Twave_window_pattern']}% of raw candidates are 150-450 ms "
        f"apart from the previous one (the failure-mode signature).\n"
        f"- **Verdict:** {r['verdict']}\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-dir", default="results", type=Path)
    ap.add_argument("--out", default="results/PI_VALIDATION_REPORT.md", type=Path)
    args = ap.parse_args()

    parts = [
        "# Raspberry Pi validation report\n",
        "Generated by pi_diagnostics/analyze_all.py. Answers the deployment gate in "
        "backend/MAD_INTEGRATION.md before this MAD-based backend replaces production.\n",
        section_fs_jitter(args.results_dir),
        section_latency(args.results_dir),
        section_resources(args.results_dir),
        section_twave(args.results_dir),
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(parts), encoding="utf-8")
    print("\n".join(parts))


if __name__ == "__main__":
    main()
