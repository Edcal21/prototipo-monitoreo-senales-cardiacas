#!/usr/bin/env python3
"""
Monitor ECG en modo profesor.

Se conecta al WebSocket del backend, toma datos reales de adquisicion y muestra
en consola las etapas principales del procesamiento como en un laboratorio:
senal cruda, linea base, correccion, filtrado, picos R, RR y BPM.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from collections import deque
from typing import Any
from urllib.parse import urlencode

import numpy as np

try:
    import websockets
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Falta el paquete 'websockets'. En la Pi instala dentro del venv: "
        "pip install websockets"
    ) from exc

try:
    from scipy import signal
except ImportError:  # pragma: no cover
    signal = None


def estimate_fs(t: np.ndarray) -> float | None:
    if t.size < 20:
        return None
    dt = np.diff(t)
    dt = dt[dt > 0]
    if dt.size < 10:
        return None
    return float(1.0 / np.mean(dt))


def safe_odd_window(target_size: float, signal_len: int) -> int:
    if signal_len <= 1:
        return 1
    win = max(1, int(round(target_size)))
    if win % 2 == 0:
        win += 1
    max_win = signal_len if signal_len % 2 == 1 else signal_len - 1
    return max(1, min(win, max_win))


def moving_average_same(x: np.ndarray, window: int) -> np.ndarray:
    window = int(max(1, min(window, len(x))))
    if window <= 1:
        return x.astype(float, copy=True)
    kernel = np.ones(window, dtype=float) / float(window)
    pad = window // 2
    padded = np.pad(x.astype(float), (pad, pad), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def baseline_correction(x: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    baseline_win = safe_odd_window(fs * 0.75, len(x))
    baseline = moving_average_same(x, baseline_win)
    corrected = x - baseline
    return baseline, corrected


def butterworth_filter(x: np.ndarray, fs: float) -> np.ndarray:
    if signal is None or x.size < 20:
        return x.astype(float, copy=True)

    nyquist = fs / 2.0
    y = x.astype(float, copy=True)

    if 60.0 < nyquist:
        b_notch, a_notch = signal.iirnotch(60.0, 30.0, fs)
        y = signal.filtfilt(b_notch, a_notch, y)

    high = min(40.0, nyquist * 0.85)
    low = 0.5
    if high <= low:
        return y

    b_band, a_band = signal.butter(2, [low, high], btype="bandpass", fs=fs)
    return signal.filtfilt(b_band, a_band, y)


def detect_r_peaks(v_clean: np.ndarray, fs: float) -> np.ndarray:
    if v_clean.size < 10:
        return np.array([], dtype=int)

    threshold = float(np.mean(v_clean) + np.std(v_clean) * 2.0)
    min_distance = max(1, int(fs * 0.5))

    if signal is not None:
        peaks, _ = signal.find_peaks(v_clean, height=threshold, distance=min_distance)
        return peaks.astype(int)

    peaks = []
    last_peak = -min_distance
    for i in range(1, len(v_clean) - 1):
        if i - last_peak < min_distance:
            continue
        if v_clean[i] > threshold and v_clean[i] > v_clean[i - 1] and v_clean[i] > v_clean[i + 1]:
            peaks.append(i)
            last_peak = i
    return np.asarray(peaks, dtype=int)


def rr_and_bpm(peaks: np.ndarray, fs: float) -> tuple[np.ndarray, float | None, float | None]:
    if peaks.size < 2:
        return np.array([], dtype=float), None, None
    rr = np.diff(peaks) / fs
    rr = rr[(rr >= 0.3) & (rr <= 2.5)]
    if rr.size == 0:
        return rr, None, None
    bpm = 60.0 / rr
    return rr, float(np.median(bpm)), float(np.mean(bpm))


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "--"
    try:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return "--"
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value)


def render_lesson(payload: dict[str, Any]) -> str:
    samples = payload.get("samples") or {}
    metrics = payload.get("metrics") or {}

    t = np.asarray(samples.get("t") or [], dtype=float)
    raw = np.asarray(samples.get("raw_v") or samples.get("v") or [], dtype=float)

    if t.size < 20 or raw.size < 20:
        return "Esperando suficientes muestras reales desde el backend..."

    if t.size != raw.size:
        n = min(t.size, raw.size)
        t = t[-n:]
        raw = raw[-n:]

    fs = estimate_fs(t) or float(metrics.get("fs_est") or 250.0)
    baseline, corrected = baseline_correction(raw, fs)
    clean = butterworth_filter(raw, fs)
    peaks = detect_r_peaks(clean, fs)
    rr, hr_median, hr_mean = rr_and_bpm(peaks, fs)

    baseline_drift_mv = (float(np.max(baseline) - np.min(baseline)) * 1000.0) if baseline.size else 0.0
    raw_span_mv = (float(np.max(raw) - np.min(raw)) * 1000.0) if raw.size else 0.0
    clean_span_mv = (float(np.max(clean) - np.min(clean)) * 1000.0) if clean.size else 0.0
    duration_s = float(t[-1] - t[0]) if t.size else 0.0

    lines = [
        "MODO PROFESOR ECG - datos reales en vivo",
        "=" * 72,
        f"Ventana recibida: {fmt(duration_s, 2)} s | Muestras: {len(raw)} | fs estimada: {fmt(fs, 2)} Hz",
        "",
        "1) ADQUISICION",
        f"   El ADC entrega x[n] en voltios. Rango crudo: {fmt(raw_span_mv, 3)} mV",
        f"   Ultima muestra: x[n] = {fmt(raw[-1], 6)} V",
        "",
        "2) LINEA BASE",
        "   Se estima la tendencia lenta b[n] con promedio movil de 0.75 s.",
        "   Formula: b[n] = promedio local de x[n]",
        f"   Deriva estimada en esta ventana: max(b)-min(b) = {fmt(baseline_drift_mv, 3)} mV",
        "",
        "3) CORRECCION DE LINEA BASE",
        "   Se resta la tendencia lenta para estabilizar la senal.",
        "   Formula: y[n] = x[n] - b[n]",
        f"   Ultima muestra corregida: y[n] = {fmt(corrected[-1], 6)} V",
        "",
        "4) FILTRADO PARA ANALISIS",
        "   Se aplica notch 60 Hz si la frecuencia de muestreo lo permite.",
        "   Luego Butterworth pasa-banda: 0.5 Hz a 40 Hz.",
        f"   Rango filtrado: {fmt(clean_span_mv, 3)} mV",
        "",
        "5) DETECCION DE PICOS R",
        "   Umbral: media(senal_filtrada) + 2*desviacion_estandar",
        "   Restriccion: distancia minima entre picos = 0.5 s",
        f"   Picos R detectados en la ventana: {len(peaks)}",
        "",
        "6) RR Y FRECUENCIA CARDIACA",
        "   RR[i] = (R[i+1] - R[i]) / fs",
        "   BPM[i] = 60 / RR[i]",
        f"   RR mediano: {fmt(float(np.median(rr)) if rr.size else None, 3)} s",
        f"   BPM mediano: {fmt(hr_median, 1)} | BPM promedio: {fmt(hr_mean, 1)}",
        "",
        "7) METRICAS DEL BACKEND",
        f"   Calidad: {metrics.get('quality', '--')} | Lead-off: {metrics.get('lead_off', '--')}",
        f"   BPM backend: {fmt(metrics.get('hr_median'), 1)} | R-peaks backend: {metrics.get('rpeaks', '--')}",
    ]
    return "\n".join(lines)


async def run(args: argparse.Namespace) -> None:
    params: dict[str, str] = {}
    if args.api_key:
        params["api_key"] = args.api_key
    else:
        params["username"] = args.username
        params["password"] = args.password

    url = f"ws://{args.host}:{args.port}/ws/ecg?{urlencode(params)}"
    recent_payloads: deque[dict[str, Any]] = deque(maxlen=1)

    while True:
        try:
            async with websockets.connect(url, ping_interval=None, close_timeout=1) as ws:
                print(f"Conectado a {url}")
                next_render = 0.0

                while True:
                    msg = await ws.recv()
                    payload = json.loads(msg)
                    recent_payloads.append(payload)

                    now = asyncio.get_running_loop().time()
                    if now < next_render:
                        continue

                    next_render = now + args.interval

                    if args.clear:
                        os.system("clear" if os.name != "nt" else "cls")

                    print(render_lesson(recent_payloads[-1]))
                    print("\nCtrl+C para salir.")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"\nConexion perdida ({exc}). Reintentando en 3 segundos...")
            await asyncio.sleep(3)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profesor ECG en tiempo real usando el WebSocket del backend.")
    parser.add_argument("--host", default="127.0.0.1", help="Host del backend.")
    parser.add_argument("--port", default=8000, type=int, help="Puerto del backend.")
    parser.add_argument("--api-key", default="", help="API key admin, por ejemplo devkey-123.")
    parser.add_argument("--username", default="fernando.flores", help="Usuario de solo lectura o admin.")
    parser.add_argument("--password", default="medinic2026", help="Contrasena del usuario.")
    parser.add_argument("--interval", default=2.0, type=float, help="Segundos entre explicaciones.")
    parser.add_argument("--no-clear", dest="clear", action="store_false", help="No limpiar pantalla entre lecturas.")
    parser.set_defaults(clear=True)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("\nSesion finalizada.")
