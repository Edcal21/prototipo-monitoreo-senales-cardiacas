#!/usr/bin/env python3
"""Analyze the raw acquisition-timestamp log produced by backend_iot.py's opt-in
ECG_DIAG_LOG_PATH logger. Answers exactly what the original audit (auditoria_backend_ecg.md)
flagged as unmeasured: effective sampling rate, jitter, and dropped/stalled samples --
configuring ADS1115 at 250 SPS and sleeping 2 ms does not by itself guarantee either.

Usage:
    python fs_jitter_report.py --in results/diag_samples.csv --out results/fs_jitter_report.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", default="results/fs_jitter_report.json")
    ap.add_argument("--configured-rate-hz", type=float, default=250.0,
                     help="ADC_DATA_RATE from backend_iot.py, for comparison")
    ap.add_argument("--gap-factor", type=float, default=3.0,
                     help="A dt more than this many times the median dt counts as a stall/gap")
    args = ap.parse_args()

    t = pd.read_csv(args.in_path)["t_monotonic_s"].to_numpy(dtype=float)
    t = np.sort(t)
    dt = np.diff(t)
    dt_ms = dt * 1000.0
    median_dt = float(np.median(dt))
    gap_threshold = args.gap_factor * median_dt
    gaps = dt[dt > gap_threshold]
    # each gap of duration g at a nominal spacing of median_dt implies (g/median_dt - 1)
    # samples were missed during that stall
    dropped_samples_est = int(np.sum(np.round(gaps / median_dt) - 1)) if len(gaps) else 0

    duration_s = float(t[-1] - t[0])
    report = {
        "input_file": args.in_path,
        "n_samples": int(len(t)),
        "duration_s": round(duration_s, 1),
        "configured_rate_hz": args.configured_rate_hz,
        "effective_fs_mean_hz": round(1.0 / float(np.mean(dt)), 2),
        "effective_fs_median_hz": round(1.0 / median_dt, 2),
        "effective_fs_vs_configured_pct": round(100 * (1.0 / float(np.mean(dt))) / args.configured_rate_hz, 1),
        "dt_ms": {
            "mean": round(float(np.mean(dt_ms)), 4),
            "sd": round(float(np.std(dt_ms, ddof=1)), 4),
            "min": round(float(np.min(dt_ms)), 4),
            "max": round(float(np.max(dt_ms)), 4),
            "p50": round(float(np.percentile(dt_ms, 50)), 4),
            "p95": round(float(np.percentile(dt_ms, 95)), 4),
            "p99": round(float(np.percentile(dt_ms, 99)), 4),
            "p999": round(float(np.percentile(dt_ms, 99.9)), 4),
        },
        "jitter_sd_ms": round(float(np.std(dt_ms, ddof=1)), 4),
        "gaps": {
            "threshold_ms": round(gap_threshold * 1000, 3),
            "count": int(len(gaps)),
            "total_stalled_time_s": round(float(np.sum(gaps)), 3),
            "estimated_dropped_samples": dropped_samples_est,
            "worst_gap_ms": round(float(np.max(gaps)) * 1000, 2) if len(gaps) else 0.0,
        },
    }

    # windowed Fs over the session (10 s bins) to see drift/thermal-throttling effects
    bins = np.arange(t[0], t[-1], 10.0)
    windowed = []
    for a, b in zip(bins[:-1], bins[1:]):
        mask = (t >= a) & (t < b)
        n = int(mask.sum())
        windowed.append({"t_start_s": round(a - t[0], 1), "n_samples": n, "fs_hz": round(n / 10.0, 2)})
    report["windowed_fs_10s_bins"] = windowed

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "windowed_fs_10s_bins"}, indent=2))
    print(f"({len(windowed)} windowed bins written to {args.out}, omitted from console output)")


if __name__ == "__main__":
    main()
