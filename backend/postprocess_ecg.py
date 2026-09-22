# Backend/postprocess_ecg.py
"""
ECG window processing: filtering, R-peak detection, HR/HRV + optional TFLite diagnosis.

Contract:
- Input: t (seconds), v (voltage), fs (target Hz)
- Output dict: hr_median, hr_mean, rpeaks, rr_s, rmssd_ms, sdnn_ms, pnn50, quality, note,
               diagnosis, confidence, snr_db, artifacts_pct, v_clean (optional)

Notes:
- This module is designed to be called from a real-time acquisition thread.
- Keep computations bounded (O(n) per window).
"""
from __future__ import annotations

import os
import random
import logging
from typing import Any, Dict, Tuple

import numpy as np
from scipy import signal

try:
    import tflite_runtime.interpreter as tflite  # type: ignore
    HAS_TFLITE = True
except ImportError:
    HAS_TFLITE = False

_INTERPRETER = None
_INPUT_DETAILS = None
_OUTPUT_DETAILS = None
LOGGER = logging.getLogger("ecg.metrics")

RR_MIN_S = 0.300
RR_MAX_S = 2.000
RMSSD_WARN_MS = 250.0
BPM_RPEAK_TOLERANCE_FRAC = 0.25
BPM_RPEAK_TOLERANCE_MIN = 3
MAD_K = float(os.getenv("ECG_MAD_K", "8.0"))
MAD_INTEGRATION_S = float(os.getenv("ECG_MAD_INTEGRATION_S", "0.150"))
MAD_REFRACTORY_S = float(os.getenv("ECG_MAD_REFRACTORY_S", "0.250"))
MAD_LOCALIZATION_S = float(os.getenv("ECG_MAD_LOCALIZATION_S", "0.150"))


def get_interpreter():
    global _INTERPRETER, _INPUT_DETAILS, _OUTPUT_DETAILS
    if not HAS_TFLITE:
        return None, None, None

    if _INTERPRETER is None:
        model_path = os.path.join(os.path.dirname(__file__), "modelo_ecg.tflite")
        try:
            if os.path.exists(model_path) and os.path.getsize(model_path) > 1000:
                _INTERPRETER = tflite.Interpreter(model_path=model_path)
                _INTERPRETER.allocate_tensors()
                _INPUT_DETAILS = _INTERPRETER.get_input_details()
                _OUTPUT_DETAILS = _INTERPRETER.get_output_details()
            else:
                return None, None, None
        except Exception:
            print("Modo Simulación: El archivo de modelo no es válido o no existe.")
            return None, None, None

    return _INTERPRETER, _INPUT_DETAILS, _OUTPUT_DETAILS


def _bandpass_notch_legacy(v: np.ndarray, fs: float) -> np.ndarray:
    # 60 Hz notch
    b_notch, a_notch = signal.iirnotch(60.0, 30.0, fs)
    v1 = signal.filtfilt(b_notch, a_notch, v)
    # 0.5–40 Hz bandpass
    b_band, a_band = signal.butter(2, [0.5, 40.0], btype="bandpass", fs=fs)
    return signal.filtfilt(b_band, a_band, v1)


def _bandpass_notch(v: np.ndarray, fs: float) -> np.ndarray:
    nyquist = fs / 2.0
    v1 = v

    if nyquist > 62.0:
        b_notch, a_notch = signal.iirnotch(60.0, 30.0, fs)
        v1 = signal.filtfilt(b_notch, a_notch, v1)

    highcut = min(40.0, nyquist * 0.80)
    if highcut <= 0.6:
        return v1 - np.mean(v1)

    b_band, a_band = signal.butter(2, [0.5, highcut], btype="bandpass", fs=fs)
    return signal.filtfilt(b_band, a_band, v1)


def _moving_average_same(x: np.ndarray, window: int) -> np.ndarray:
    if len(x) < 3 or window <= 1:
        return x.astype(float, copy=True)
    if window % 2 == 0:
        window += 1
    window = min(window, len(x) if len(x) % 2 else len(x) - 1)
    kernel = np.ones(window, dtype=float) / float(window)
    pad = window // 2
    return np.convolve(np.pad(x, (pad, pad), mode="edge"), kernel, mode="valid")


def mad_filter_ecg(v: np.ndarray, fs: float) -> np.ndarray:
    """Filter used by the deployed MAD detector in every backend output path."""
    v = np.asarray(v, dtype=float)
    nyquist = fs / 2.0
    highcut = min(40.0, nyquist * 0.80)
    if v.size < max(5, int(fs * 2)) or highcut <= 0.6:
        return v - np.mean(v) if v.size else v.copy()
    b_band, a_band = signal.butter(2, [0.5, highcut], btype="bandpass", fs=fs)
    return signal.filtfilt(b_band, a_band, v)


def detect_mad_r_peaks(v_clean: np.ndarray, fs: float, k: float = MAD_K) -> np.ndarray:
    """Detect R peaks using derivative energy and median + k*MAD thresholding.

    Input must already be filtered with :func:`mad_filter_ecg`.
    """
    v_clean = np.asarray(v_clean, dtype=float)
    if v_clean.size < max(5, int(fs * 2)):
        return np.array([], dtype=int)
    energy = np.diff(v_clean, prepend=v_clean[0]) ** 2
    integrated = _moving_average_same(energy, max(1, int(round(MAD_INTEGRATION_S * fs))))
    median = float(np.median(integrated))
    mad = float(np.median(np.abs(integrated - median)))
    threshold = median + float(k) * max(mad, np.finfo(float).eps)
    candidates, _ = signal.find_peaks(
        integrated,
        height=threshold,
        distance=max(1, int(MAD_REFRACTORY_S * fs)),
    )

    search = max(1, int(MAD_LOCALIZATION_S * fs))
    localized = []
    for candidate in candidates:
        lo = max(0, int(candidate) - search)
        hi = min(len(v_clean), int(candidate) + search + 1)
        localized.append(lo + int(np.argmax(np.abs(v_clean[lo:hi]))))

    refractory = max(1, int(MAD_REFRACTORY_S * fs))
    accepted: list[int] = []
    for peak in sorted(set(localized)):
        if not accepted or peak - accepted[-1] >= refractory:
            accepted.append(peak)
        elif abs(v_clean[peak]) > abs(v_clean[accepted[-1]]):
            accepted[-1] = peak
    return np.asarray(accepted, dtype=int)


def windowed_mad_pipeline(v_mv: np.ndarray, fs: float, window_s: float = 10.0) -> Tuple[np.ndarray, np.ndarray]:
    """Filter + detect over non-overlapping `window_s` tiles.

    The live metrics and monitor paths never see more than the last `window_s` seconds:
    they filter and detect on a rolling buffer, recomputed from scratch every update tick.
    This reconstructs the same unit of processing for an already-recorded (exported)
    session, instead of running mad_filter_ecg/detect_mad_r_peaks once over the whole
    session with a single global median/MAD threshold (see VERIFICACION_INTEGRACION_MAD.md
    for the measured effect of that difference on MIT-BIH). Tiling matches
    mitdb_eval/detectors.py::window_edges/run_windowed, the scheme actually validated.

    Returns (filtered_mv, peak_indices): `filtered_mv` has the same length as `v_mv`
    (each sample filtered as part of its own window); `peak_indices` are global sample
    indices into `v_mv`.
    """
    v_mv = np.asarray(v_mv, dtype=float)
    n = v_mv.size
    min_len = max(5, int(fs * 2))
    if n < min_len:
        return v_mv.copy(), np.array([], dtype=int)

    w = max(min_len, int(round(window_s * fs)))
    edges: list[tuple[int, int, int]] = []
    pos = 0
    while pos + w <= n:
        edges.append((pos, pos + w, pos))
        pos += w
    if pos < n:
        start = max(0, n - w)
        edges.append((start, n, pos))

    filtered = np.empty(n, dtype=float)
    peaks: list[int] = []
    for start, end, keep_from in edges:
        seg_filtered = mad_filter_ecg(v_mv[start:end], fs)
        filtered[start:end] = seg_filtered
        seg_peaks = detect_mad_r_peaks(seg_filtered, fs) + start
        peaks.extend(int(p) for p in seg_peaks if keep_from <= p < end)

    return filtered, np.asarray(sorted(set(peaks)), dtype=int)


def _rr_from_peaks(peaks: np.ndarray, fs: float) -> np.ndarray:
    if len(peaks) < 2:
        return np.array([], dtype=float)
    rr = np.diff(peaks) / fs
    rr = rr[(rr >= RR_MIN_S) & (rr <= RR_MAX_S)]
    return rr


def _valid_peaks_and_rr(peaks: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
    if len(peaks) < 2:
        return np.array([], dtype=int), np.array([], dtype=float)

    rr_all = np.diff(peaks) / fs
    valid_interval_mask = (rr_all >= RR_MIN_S) & (rr_all <= RR_MAX_S)
    if not np.any(valid_interval_mask):
        return np.array([], dtype=int), np.array([], dtype=float)

    valid_peak_positions = set()
    for idx, is_valid in enumerate(valid_interval_mask):
        if is_valid:
            valid_peak_positions.add(idx)
            valid_peak_positions.add(idx + 1)

    valid_peaks = peaks[sorted(valid_peak_positions)].astype(int)
    valid_rr = rr_all[valid_interval_mask].astype(float)
    return valid_peaks, valid_rr


def _hr_from_rr(rr: np.ndarray) -> Tuple[float | None, float | None]:
    if rr.size == 0:
        return None, None
    hr_inst = 60.0 / rr
    return float(np.median(hr_inst)), float(np.mean(hr_inst))


def _rmssd_ms(rr: np.ndarray) -> float | None:
    if rr.size < 2:
        return None
    diff = np.diff(rr)
    return float(np.sqrt(np.mean(diff * diff)) * 1000.0)


def _sdnn_ms(rr: np.ndarray) -> float | None:
    if rr.size < 2:
        return None
    return float(np.std(rr, ddof=1) * 1000.0)


def _pnn50(rr: np.ndarray) -> float | None:
    if rr.size < 2:
        return None
    diff_ms = np.abs(np.diff(rr)) * 1000.0
    return float(np.mean(diff_ms > 50.0) * 100.0)


def _analysis_duration_sec(t: Any, sample_count: int, fs: float) -> float:
    try:
        t_arr = np.asarray(t, dtype=float)
        if t_arr.size >= 2:
            duration = float(t_arr[-1] - t_arr[0])
            if duration > 0:
                return duration
    except Exception:
        pass
    return float(sample_count / max(fs, 1e-9))


def _validate_metric_consistency(
    *,
    duration_sec: float,
    rpeaks: int,
    bpm: float | None,
    rmssd_ms: float | None,
) -> list[str]:
    warnings: list[str] = []

    if rmssd_ms is not None and rmssd_ms > RMSSD_WARN_MS:
        warnings.append(f"RMSSD alto para ECG de reposo: {rmssd_ms:.1f} ms")

    if duration_sec > 0 and bpm is not None and rpeaks > 0:
        expected_peaks = bpm * duration_sec / 60.0
        tolerance = max(BPM_RPEAK_TOLERANCE_MIN, expected_peaks * BPM_RPEAK_TOLERANCE_FRAC)
        if abs(rpeaks - expected_peaks) > tolerance:
            warnings.append(
                "BPM y picos R inconsistentes: "
                f"bpm={bpm:.1f}, duracion={duration_sec:.2f}s, "
                f"picos={rpeaks}, esperado={expected_peaks:.1f}"
            )

    for message in warnings:
        LOGGER.warning(message)
    return warnings


def _snr_db(v_clean: np.ndarray) -> float | None:
    # Very rough SNR proxy:
    # signal power = var(filtered), noise proxy = var(high-frequency residual)
    if v_clean.size < 10:
        return None
    # Residual via simple lowpass to estimate baseline
    b_lp, a_lp = signal.butter(2, 5.0, btype="lowpass", fs=250.0)
    baseline = signal.filtfilt(b_lp, a_lp, v_clean)
    resid = v_clean - baseline
    sig = float(np.var(v_clean) + 1e-12)
    noi = float(np.var(resid) + 1e-12)
    return float(10.0 * np.log10(sig / noi))


def _artifacts_pct(v_clean: np.ndarray, fs: float) -> float | None:
    # Simple artifact proxy: % of samples beyond 6-sigma
    if v_clean.size < 10:
        return None
    mu = float(np.mean(v_clean))
    sd = float(np.std(v_clean) + 1e-12)
    z = np.abs((v_clean - mu) / sd)
    return float(np.mean(z > 6.0) * 100.0)


def process_window(t, v, fs: float = 250.0, thr_norm: float = 0.12) -> Dict[str, Any]:
    v = np.asarray(v, dtype=float)
    duration_sec = _analysis_duration_sec(t, int(v.size), fs)
    if v.size < int(fs * 2):
        return {
            "hr_median": None,
            "hr_mean": None,
            "rpeaks": 0,
            "raw_rpeaks": 0,
            "analysis_duration_sec": round(duration_sec, 2),
            "quality": "no_data",
            "note": "Esperando...",
            "rr_s": [],
            "valid_rr_count": 0,
            "rmssd_ms": None,
            "sdnn_ms": None,
            "pnn50": None,
            "metric_warnings": [],
            "diagnosis": "Esperando...",
            "confidence": None,
            "snr_db": None,
            "artifacts_pct": None,
            "v_clean": [],
        }

    # Unified MAD pipeline used by metrics, WebSocket markers, and exports.
    v_clean = mad_filter_ecg(v, fs)

    # Peaks/HR/HRV
    raw_peaks = detect_mad_r_peaks(v_clean, fs)
    peaks, rr = _valid_peaks_and_rr(raw_peaks, fs)
    hr_median, hr_mean = _hr_from_rr(rr)

    rmssd = _rmssd_ms(rr)
    sdnn = _sdnn_ms(rr)
    pnn50 = _pnn50(rr)
    metric_warnings = _validate_metric_consistency(
        duration_sec=duration_sec,
        rpeaks=int(len(peaks)),
        bpm=hr_median,
        rmssd_ms=rmssd,
    )

    quality = "good" if len(peaks) >= 3 and rr.size >= 2 and not metric_warnings else "low"
    note = "; ".join(metric_warnings)

    # SNR & artifacts (simple proxies)
    snr_db = _snr_db(v_clean)
    artifacts_pct = _artifacts_pct(v_clean, fs)

    # Diagnosis (TFLite if available)
    interpreter, in_details, out_details = get_interpreter()
    if interpreter:
        try:
            target_len = 2500
            v_norm = (v_clean - np.mean(v_clean)) / (np.std(v_clean) + 1e-8)
            v_input = v_norm[:target_len] if len(v_norm) >= target_len else np.pad(v_norm, (0, target_len - len(v_norm)))
            features = np.zeros(6, dtype=np.float32)

            interpreter.set_tensor(in_details[0]["index"], v_input.reshape(1, -1, 1).astype(np.float32))
            interpreter.set_tensor(in_details[1]["index"], features.reshape(1, -1))
            interpreter.invoke()
            preds = interpreter.get_tensor(out_details[0]["index"])

            classes = ["Normal", "Fibrilación Auricular", "Taquicardia"]
            diagnosis = classes[int(np.argmax(preds))]
            confidence = float(np.max(preds))
        except Exception:
            diagnosis, confidence = random.choice([("Normal", 0.98), ("Arritmia Detectada", 0.85)]), 0.90
    else:
        # Simulation fallback
        if hr_median is None:
            diagnosis = "Sin Señal"
        elif hr_median > 100:
            diagnosis = "Taquicardia (Simulado)"
        elif hr_median < 50:
            diagnosis = "Bradicardia (Simulado)"
        else:
            diagnosis = "Ritmo Sinusal (Simulado)"
        confidence = 0.95

    return {
        "hr_median": None if hr_median is None else round(hr_median, 1),
        "hr_mean": None if hr_mean is None else round(hr_mean, 1),
        "rpeaks": int(len(peaks)),
        "raw_rpeaks": int(len(raw_peaks)),
        "analysis_duration_sec": round(duration_sec, 2),
        "quality": quality,
        "detector": "mad",
        "detector_k": MAD_K,
        "detector_refractory_ms": round(MAD_REFRACTORY_S * 1000.0, 1),
        "note": note,
        "rr_s": rr.tolist(),
        "valid_rr_count": int(rr.size),
        "rmssd_ms": None if rmssd is None else round(rmssd, 1),
        "sdnn_ms": None if sdnn is None else round(sdnn, 1),
        "pnn50": None if pnn50 is None else round(pnn50, 1),
        "metric_warnings": metric_warnings,
        "diagnosis": diagnosis,
        "confidence": None if confidence is None else round(float(confidence), 2),
        "snr_db": None if snr_db is None else round(float(snr_db), 1),
        "artifacts_pct": None if artifacts_pct is None else round(float(artifacts_pct), 1),
        "v_clean": v_clean.tolist(),
    }
