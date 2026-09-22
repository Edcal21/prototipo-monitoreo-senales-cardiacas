#!/usr/bin/env python3
"""Check a recorded session for the T-wave double-detection mode found on MIT-BIH record 113
(see mitdb_eval/results/final_48/twave_mode_record113.json in the evaluation repo): a second,
spurious peak accepted 150-450 ms after a true beat, inside the derivative-energy feature's
own MAD threshold, which the 250 ms refractory period does not suppress.

Works on an exported session's .dat file (from build_session_export_zip_bytes: columns
index, time_s, value_v, value_mV -- no header) or any two-column time,voltage CSV.

Usage (run on the Pi, or anywhere with the backend/ package importable):
    python check_twave_mode.py --dat path/to/RECORD.dat --fs 250 --out results/twave_check.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
import postprocess_ecg as pp  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dat", required=True, help="Exported .dat CSV (index,time_s,value_v,value_mv)")
    ap.add_argument("--fs", type=float, required=True, help="Sampling rate the session was stored at")
    ap.add_argument("--time-col", type=int, default=1)
    ap.add_argument("--value-col", type=int, default=2)
    ap.add_argument("--out", default="results/twave_check.json")
    args = ap.parse_args()

    raw = np.loadtxt(args.dat, delimiter=",")
    t = raw[:, args.time_col]
    v = raw[:, args.value_col] * 1000.0  # to mV, matching the mad_filter_ecg input scale used live
    fs = args.fs

    filtered, raw_peaks = pp.windowed_mad_pipeline(v, fs, window_s=10.0)
    valid_peaks, valid_rr = pp._valid_peaks_and_rr(raw_peaks, fs)

    n_raw, n_valid = len(raw_peaks), len(valid_peaks)
    rejected = n_raw - n_valid

    # among raw peaks, how many are 150-450 ms after the PREVIOUS raw peak (the T-wave
    # timing signature found on record 113)?
    twave_like = 0
    if n_raw > 1:
        rr_prev = np.diff(raw_peaks) / fs
        twave_like = int(np.sum((rr_prev >= 0.150) & (rr_prev <= 0.450)))

    pct_twave = round(100 * twave_like / n_raw, 1) if n_raw else None
    report = {
        "input": args.dat,
        "fs_hz": fs,
        "duration_s": round(float(t[-1] - t[0]), 1) if len(t) > 1 else 0.0,
        "raw_peaks": n_raw,
        "valid_peaks_after_RR_filter": n_valid,
        "peaks_rejected_by_RR_filter": rejected,
        "pct_rejected": round(100 * rejected / n_raw, 1) if n_raw else None,
        "raw_peak_pairs_150_450ms_apart": twave_like,
        "pct_raw_peaks_in_Twave_window_pattern": pct_twave,
        "note_on_RR_filter": (
            "peaks_rejected_by_RR_filter is NOT a reliable indicator of this failure mode: "
            "_valid_peaks_and_rr keeps a peak if EITHER neighboring RR interval is valid, so a "
            "spurious T-wave peak commonly survives because its interval to the NEXT true beat "
            "still looks physiological. Validated against MIT-BIH record 113 (see "
            "mitdb_eval/results/final_48/twave_mode_record113.json), where 46.8% of raw "
            "candidates showed this spacing but only 1 of 3356 was rejected. Trust "
            "pct_raw_peaks_in_Twave_window_pattern, not the rejection count."
        ),
        "verdict": (
            "LIKELY T-WAVE DOUBLE-DETECTION MODE PRESENT: a large share of raw candidates are "
            "150-450 ms apart. This will NOT reliably show up as a raw-vs-valid peak-count gap; "
            "instead expect hr_median to be pulled toward roughly double the true heart rate. "
            "Cross-check against a manual pulse count for this session."
            if n_raw and (twave_like / n_raw) > 0.10
            else "No strong T-wave double-detection signature found in this session."
        ),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
