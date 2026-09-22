import uuid
import base64
import os
import subprocess
import sys
import threading
import time
import json
import socket
import csv
import re
import zipfile
import sqlite3
import threading
import logging
import psutil
from io import BytesIO, StringIO
from datetime import datetime
from logging.handlers import RotatingFileHandler
from collections import deque
from typing import Deque, Optional, Dict, Any
from pathlib import Path

import asyncio
import numpy as np
import RPi.GPIO as GPIO
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor


from pydantic import BaseModel, Field
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from adafruit_ads1x15.analog_in import AnalogIn

from postprocess_ecg import MAD_K, detect_mad_r_peaks, mad_filter_ecg, process_window, windowed_mad_pipeline
from session_store import init_sessions_db, start_session, stop_session, list_sessions
from patient_store import init_db, upsert_patient, get_patient, list_patients

try:
    from scipy import signal as scipy_signal
except Exception:
    scipy_signal = None


DB_PATH = os.getenv("ECG_DB_PATH", "data/ecg.db")

SENSOR_NAME = "AD8232 ECG Sensor"
I2C_ADDRESS = 0x48
ADC_CHANNEL = 0
ADC_DATA_RATE = 250
BATTERY_ADC_CHANNEL = int(os.getenv("ECG_BATTERY_ADC_CHANNEL", "1"))
BATTERY_R1_OHMS = float(os.getenv("ECG_BATTERY_R1_OHMS", "100000"))
BATTERY_R2_OHMS = float(os.getenv("ECG_BATTERY_R2_OHMS", "42000"))
BATTERY_EMPTY_V = float(os.getenv("ECG_BATTERY_EMPTY_V", "4.4"))
BATTERY_FULL_V = float(os.getenv("ECG_BATTERY_FULL_V", "5.0"))

BUFFER_S = 25.0
WINDOW_S = 10.0
UPDATE_EVERY_S = 2.0
FS_TARGET = 250.0
THR_NORM = 0.12
RR_MIN_S = 0.300
RR_MAX_S = 2.000
RMSSD_WARN_MS = 250.0
BPM_RPEAK_TOLERANCE_FRAC = 0.25
BPM_RPEAK_TOLERANCE_MIN = 3

API_KEY = os.getenv("ECG_API_KEY", "devkey-123")
DEMO_LOOP_ENABLED = os.getenv("ECG_DEMO_LOOP", "1").strip().lower() not in {"0", "false", "no", "off"}
DEMO_LOOP_UPDATE_MIN_S = float(os.getenv("ECG_DEMO_LOOP_UPDATE_MIN_S", "20"))
READ_ONLY_API_KEYS = {
    "lectura1": os.getenv("ECG_READONLY_KEY_1", "readonly-001"),
    "lectura2": os.getenv("ECG_READONLY_KEY_2", "readonly-002"),
    "lectura3": os.getenv("ECG_READONLY_KEY_3", "readonly-003"),
}
PASSWORD_USERS = {
    "fernando.flores": {
        "username": "fernando.flores",
        "password": os.getenv("ECG_FERNANDO_FLORES_PASSWORD", "medinic2026"),
        "role": "read_only",
        "can_record_ecg": False,
    },
    "jaime.alvarez": {
        "username": "jaime.alvarez",
        "password": os.getenv("ECG_JAIME_ALVAREZ_PASSWORD", "medinic2026"),
        "role": "read_only",
        "can_record_ecg": False,
    },
    "imer.diaz": {
        "username": "imer.diaz",
        "password": os.getenv("ECG_IMER_DIAZ_PASSWORD", "medinic2026"),
        "role": "read_only",
        "can_record_ecg": False,
    },
}
API_USERS = {
    API_KEY: {"username": "admin", "role": "admin", "can_record_ecg": True},
}
API_USERS.update(
    {
        key: {"username": username, "role": "read_only", "can_record_ecg": False}
        for username, key in READ_ONLY_API_KEYS.items()
        if key
    }
)

GPIO_LO_PLUS = 17
GPIO_LO_MINUS = 27
GPIO_SDN = 26

LEAD_OFF_ACTIVE_HIGH = True
LEAD_OFF_CONFIRM_MS = 400

_lead_off_state = False
_lead_off_last_instant = None
_lead_off_last_change_ts = time.monotonic()
AUTO_SHUTDOWN_ON_LEAD_OFF = True
LEAD_OFF_DEBOUNCE_N = 3

REPORT_SPEED = "25 mm/s"
REPORT_GAIN = "10 mm/mV"
REPORT_LEAD = "Lead I"


def get_rpi_model() -> str:
    try:
        with open("/proc/device-tree/model", "r", encoding="utf-8") as f:
            return f.read().replace("\x00", "").strip()
    except Exception:
        return "Raspberry Pi"



def get_temperature_c() -> float | None:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r", encoding="utf-8") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        return None


def get_uptime_s() -> float | None:
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            return round(float(f.read().split()[0]), 1)
    except Exception:
        return None


def get_system_status_payload() -> dict:
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_percent = psutil.cpu_percent(interval=0.2)
    temp_c = get_temperature_c()
    uptime_s = get_uptime_s()

    with STATE.lock:
        metrics = dict(STATE.last_metrics)

    return {
        "ok": True,
        "cpu_percent": round(cpu_percent, 1),
        "ram_percent": round(vm.percent, 1),
        "ram_used_mb": round(vm.used / (1024 * 1024), 1),
        "ram_total_mb": round(vm.total / (1024 * 1024), 1),
        "disk_percent": round(disk.percent, 1),
        "disk_used_gb": round(disk.used / (1024 * 1024 * 1024), 2),
            "disk_total_gb": round(disk.total / (1024 * 1024 * 1024), 2),
            "temperature_c": temp_c,
            "uptime_s": uptime_s,
            "battery_pct": metrics.get("battery_pct"),
            "battery_voltage_v": metrics.get("battery_voltage_v"),
            "battery_adc_voltage_v": metrics.get("battery_adc_voltage_v"),
            "backend_ok": True,
        "adc_ok": bool(STATE.hw_ok),
        "adc_error": STATE.hw_error,
        "clients": STATE.clients,
        "record_id": metrics.get("record_id"),
        "quality": metrics.get("quality"),
        "lead_off": metrics.get("lead_off"),
        "fs_est": metrics.get("fs_est"),
    }


def get_gateway_name() -> str:
    return f"{get_rpi_model()} ({socket.gethostname()})"


GATEWAY_NAME = get_gateway_name()

os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("iot_backend")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = RotatingFileHandler("logs/backend.log", maxBytes=2_000_000, backupCount=5)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)


def log_event(event: str, extra: str = ""):
    logger.info(f"event={event} {extra}".strip())


class SharedState:
    def __init__(self):
        self.lock = threading.Lock()
        self.buf_t: Deque[float] = deque()
        self.buf_v: Deque[float] = deque()
        self.running = False
        self.recording = False
        self.hw_ok = False
        self.hw_error = ""
        self.last_hw_error = ""
        self.hw_recovered = False
        self.clients = 0
        self.current_record_context: Dict[str, Any] = {}
        self.last_good_metrics: Dict[str, Any] = {}
        self.demo_loop: Dict[str, Any] | None = None
        self.wall_start: float = 0.0  # time.time() taken alongside acquisition_worker's t_start

        self.last_metrics: Dict[str, Any] = {
            "record_id": None,
            "patient_name": None,
            "patient_identifier": None,
            "age": None,
            "sex": None,
            "lead": REPORT_LEAD,
            "study_date": None,
            "speed": REPORT_SPEED,
            "gain": REPORT_GAIN,
            "duration": None,
            "interpretation": None,
            "ecg_file_reference": None,
            "device": SENSOR_NAME,
            "gateway": GATEWAY_NAME,
            "ts": None,
            "fs_est": None,
            "adc_channel": ADC_CHANNEL,
            "adc_data_rate": ADC_DATA_RATE,
            "hw_ok": False,
            "hw_error": "",
            "last_hw_error": "",
            "hw_recovered": False,
            "clients": 0,
            "hr_median": None,
            "hr_mean": None,
            "rpeaks": 0,
            "quality": "unknown",
            "note": "",
            "rr_s": [],
            "sdnn_ms": None,
            "rmssd_ms": None,
            "pnn50": None,
            "lead_off": None,
            "lo_plus": None,
            "lo_minus": None,
            "sdn": None,
            "snr_db": None,
            "artifacts_pct": None,
            "battery_pct": None,
            "battery_voltage_v": None,
            "battery_adc_voltage_v": None,
            "signal_mode": "filtered",
        }


STATE = SharedState()


def db_connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def init_record_sequence_db():
    conn = db_connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS record_sequence (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                last_value INTEGER NOT NULL
            )
            """
        )
        conn.execute("INSERT OR IGNORE INTO record_sequence (singleton, last_value) VALUES (1, 0)")
    finally:
        conn.close()


def next_record_id() -> str:
    conn = db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT last_value FROM record_sequence WHERE singleton = 1").fetchone()
        last_value = int(row["last_value"])
        new_value = last_value + 1
        conn.execute("UPDATE record_sequence SET last_value = ? WHERE singleton = 1", (new_value,))
        conn.commit()
        return f"ECG-{new_value:06d}"
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def gpio_setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(GPIO_LO_PLUS, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(GPIO_LO_MINUS, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(GPIO_SDN, GPIO.OUT)
    GPIO.output(GPIO_SDN, GPIO.HIGH)


def read_lead_off() -> Dict[str, bool]:
    global _lead_off_state, _lead_off_last_instant, _lead_off_last_change_ts

    lo_p = GPIO.input(GPIO_LO_PLUS)
    lo_m = GPIO.input(GPIO_LO_MINUS)
    instant_lead_off = bool(lo_p or lo_m) if LEAD_OFF_ACTIVE_HIGH else not (bool(lo_p) and bool(lo_m))

    now = time.monotonic()

    if _lead_off_last_instant is None or instant_lead_off != _lead_off_last_instant:
        _lead_off_last_instant = instant_lead_off
        _lead_off_last_change_ts = now
    else:
        elapsed_ms = (now - _lead_off_last_change_ts) * 1000.0
        if elapsed_ms >= LEAD_OFF_CONFIRM_MS:
            _lead_off_state = instant_lead_off

    return {"lead_off": _lead_off_state, "lo_plus": bool(lo_p), "lo_minus": bool(lo_m)}


def set_sdn(enabled: bool):
    GPIO.output(GPIO_SDN, GPIO.HIGH if enabled else GPIO.LOW)


def battery_percent_from_voltage(voltage: float) -> float:
    if BATTERY_FULL_V <= BATTERY_EMPTY_V:
        return 0.0
    pct = (voltage - BATTERY_EMPTY_V) * 100.0 / (BATTERY_FULL_V - BATTERY_EMPTY_V)
    return round(max(0.0, min(100.0, pct)), 1)


def read_battery_payload(chan) -> Dict[str, float | None]:
    try:
        samples = [float(chan.voltage) for _ in range(7)]
        adc_voltage = float(np.median(samples))
        battery_voltage = adc_voltage * (BATTERY_R1_OHMS + BATTERY_R2_OHMS) / BATTERY_R2_OHMS
        return {
            "battery_adc_voltage_v": round(adc_voltage, 4),
            "battery_voltage_v": round(battery_voltage, 3),
            "battery_pct": battery_percent_from_voltage(battery_voltage),
        }
    except Exception as e:
        log_event("battery_read_error", str(e))
        return {
            "battery_adc_voltage_v": None,
            "battery_voltage_v": None,
            "battery_pct": None,
        }


def get_api_user_from_key(api_key: str) -> Dict[str, Any]:
    user = API_USERS.get(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def public_user_payload(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "username": user.get("username"),
        "role": user.get("role"),
        "can_record_ecg": bool(user.get("can_record_ecg")),
    }


def get_user_from_credentials(username: str, password: str) -> Dict[str, Any]:
    user = PASSWORD_USERS.get((username or "").strip().lower())
    if not user or password != user.get("password"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return public_user_payload(user)


def get_basic_auth_credentials(request: Request) -> tuple[str, str] | None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
        username, password = decoded.split(":", 1)
        return username, password
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")


def require_api_key(request: Request) -> Dict[str, Any]:
    api_key = request.headers.get("x-api-key", "")
    if api_key:
        return get_api_user_from_key(api_key)

    username = request.headers.get("x-username", "")
    password = request.headers.get("x-password", "")
    if username or password:
        return get_user_from_credentials(username, password)

    basic_credentials = get_basic_auth_credentials(request)
    if basic_credentials:
        return get_user_from_credentials(*basic_credentials)

    raise HTTPException(status_code=401, detail="Unauthorized")


def require_write_access(request: Request) -> Dict[str, Any]:
    user = require_api_key(request)
    if not user.get("can_record_ecg"):
        raise HTTPException(status_code=403, detail="Usuario de solo lectura: no puede grabar ECG ni modificar datos.")
    return user


def estimate_fs(t: np.ndarray) -> Optional[float]:
    if len(t) < 20:
        return None
    dt = np.diff(t)
    dt = dt[dt > 0]
    if len(dt) < 10:
        return None
    return float(1.0 / np.mean(dt))


def _safe_odd_window(target_size: float, signal_len: int) -> int:
    if signal_len <= 1:
        return 1
    win = max(1, int(round(target_size)))
    if win % 2 == 0:
        win += 1
    max_win = signal_len if signal_len % 2 == 1 else signal_len - 1
    return max(1, min(win, max_win))


DIAG_LOG_PATH = os.getenv("ECG_DIAG_LOG_PATH", "").strip()
DIAG_LOG_FLUSH_N = int(os.getenv("ECG_DIAG_LOG_FLUSH_N", "500"))
_diag_buf: list[float] = []
_diag_file = None


def _diag_log_sample(t_mono: float) -> None:
    """Opt-in raw acquisition-timestamp logger for the effective-Fs/jitter/dropped-sample
    diagnostic (see pi_diagnostics/RUNBOOK.md). No-op unless ECG_DIAG_LOG_PATH is set, so it
    has zero effect on production behavior by default. Writes are batched (DIAG_LOG_FLUSH_N
    samples per flush) to avoid adding per-sample disk I/O to the acquisition loop."""
    global _diag_file
    if not DIAG_LOG_PATH:
        return
    if _diag_file is None:
        _diag_file = open(DIAG_LOG_PATH, "a", buffering=1 << 16, encoding="utf-8")
        if _diag_file.tell() == 0:
            _diag_file.write("t_monotonic_s\n")
    _diag_buf.append(t_mono)
    if len(_diag_buf) >= DIAG_LOG_FLUSH_N:
        _diag_file.write("\n".join(f"{x:.6f}" for x in _diag_buf) + "\n")
        _diag_file.flush()
        _diag_buf.clear()


def moving_average_same(x: np.ndarray, window: int) -> np.ndarray:
    if len(x) == 0 or window <= 1 or len(x) < 3:
        return x.astype(float, copy=True)
    kernel = np.ones(window, dtype=float) / float(window)
    pad = window // 2
    padded = np.pad(x.astype(float), (pad, pad), mode="edge")
    return np.convolve(padded, kernel, mode="valid")



def filter_ecg_signal(v: np.ndarray, fs_in: Optional[float]) -> np.ndarray:
    if len(v) < 5:
        return v.astype(float, copy=True)

    fs = max(25.0, float(fs_in or FS_TARGET))
    x = v.astype(float)
    baseline = moving_average_same(x, _safe_odd_window(fs * 0.75, len(x)))
    hp = x - baseline
    smoothed = moving_average_same(hp, _safe_odd_window(fs * 0.03, len(hp)))
    return moving_average_same(smoothed, _safe_odd_window(5, len(smoothed)))


def prepare_monitor_signal(t: np.ndarray, v: np.ndarray, fs_in: Optional[float]) -> tuple[np.ndarray, np.ndarray, list[float]]:
    if len(t) < 5 or len(v) < 5:
        return t.astype(float, copy=True), v.astype(float, copy=True), []

    if scipy_signal is None:
        filtered = filter_ecg_signal(v, fs_in)
        return t.astype(float, copy=True), filtered, []

    fs_source = max(25.0, float(fs_in or FS_TARGET))
    fs_target = 250.0
    t0 = float(t[0])
    t1 = float(t[-1])
    if t1 <= t0:
        return t.astype(float, copy=True), filter_ecg_signal(v, fs_in), []

    n_target = max(8, int(round((t1 - t0) * fs_target)) + 1)
    t_uniform = np.linspace(t0, t1, n_target)

    x = np.interp(t_uniform, t.astype(float), v.astype(float))
    x = x - float(np.median(x))

    try:
        n_resampled = max(8, int(round(len(x) * fs_target / fs_source)))
        x = scipy_signal.resample(x, n_resampled)
        t_uniform = np.linspace(t0, t1, n_resampled)
    except Exception:
        pass

    try:
        filtered = mad_filter_ecg(x, fs_target)
    except Exception:
        filtered = filter_ecg_signal(x, fs_target)

    filtered = filtered - float(np.median(filtered))

    rpeak_times: list[float] = []
    try:
        peaks = detect_mad_r_peaks(filtered, fs_target)
        rpeak_times = [float(t_uniform[int(p)]) for p in peaks]
    except Exception:
        rpeak_times = []

    return t_uniform, filtered, rpeak_times


def is_stable_monitor_window(filtered: np.ndarray, rpeak_times: list[float], metrics: Dict[str, Any]) -> bool:
    if not DEMO_LOOP_ENABLED:
        return False
    if STATE.demo_loop is not None and (time.time() - float(STATE.demo_loop.get("stored_at", 0))) < DEMO_LOOP_UPDATE_MIN_S:
        return False
    if len(filtered) < 50:
        return False
    if metrics.get("lead_off") is True or metrics.get("hw_ok") is False:
        return False

    span = float(np.percentile(filtered, 95) - np.percentile(filtered, 5))
    return span > 0.005


def build_demo_frozen_metrics(metrics: Dict[str, Any], rpeak_times: list[float]) -> Dict[str, Any]:
    frozen = dict(metrics)
    times = np.asarray(rpeak_times, dtype=float)
    duration = float(metrics.get("analysis_duration_sec") or 0.0)
    if duration <= 0 and len(times) >= 2:
        duration = float(max(0.0, times[-1] - times[0]))

    if len(times) >= 2:
        rr_all = np.diff(times)
        valid_mask = (rr_all >= RR_MIN_S) & (rr_all <= RR_MAX_S)
        rr = rr_all[valid_mask]
        valid_peak_indices = set()
        for idx, is_valid in enumerate(valid_mask):
            if bool(is_valid):
                valid_peak_indices.add(idx)
                valid_peak_indices.add(idx + 1)
        valid_rpeaks = len(valid_peak_indices)
    else:
        rr = np.array([], dtype=float)
        valid_rpeaks = 0

    frozen["rpeaks"] = int(valid_rpeaks)
    frozen["raw_rpeaks"] = int(len(times))
    frozen["analysis_duration_sec"] = round(duration, 2) if duration > 0 else None
    frozen["valid_rr_count"] = int(len(rr))
    frozen["metric_warnings"] = []

    if len(rr) > 0:
        bpm_values = 60.0 / rr
        hr_median = float(np.median(bpm_values))
        hr_mean = float(np.mean(bpm_values))
        frozen["hr_median"] = round(hr_median, 1)
        frozen["hr_mean"] = round(hr_mean, 1)

    if len(rr) >= 2:
        diff = np.diff(rr)
        rmssd_ms = float(np.sqrt(np.mean(diff * diff)) * 1000.0)
        frozen["rmssd_ms"] = round(rmssd_ms, 1)
        frozen["sdnn_ms"] = round(float(np.std(rr, ddof=1) * 1000.0), 1)
        frozen["pnn50"] = round(float(np.mean(np.abs(diff) > 0.05) * 100.0), 1)
        if rmssd_ms > RMSSD_WARN_MS:
            frozen["metric_warnings"].append(f"RMSSD alto para ECG de reposo: {rmssd_ms:.1f} ms")

    bpm = frozen.get("hr_median")
    if duration > 0 and bpm not in (None, "") and valid_rpeaks > 0:
        expected_peaks = float(bpm) * duration / 60.0
        tolerance = max(BPM_RPEAK_TOLERANCE_MIN, expected_peaks * BPM_RPEAK_TOLERANCE_FRAC)
        if abs(valid_rpeaks - expected_peaks) > tolerance:
            frozen["metric_warnings"].append(
                "BPM y picos R inconsistentes: "
                f"bpm={float(bpm):.1f}, duracion={duration:.2f}s, "
                f"picos={valid_rpeaks}, esperado={expected_peaks:.1f}"
            )

    for warning in frozen["metric_warnings"]:
        log_event("metric_warning", warning)

    frozen["quality"] = "good" if valid_rpeaks >= 3 and len(rr) >= 2 and not frozen["metric_warnings"] else "low"

    return frozen


def store_demo_loop(
    t: np.ndarray,
    filtered: np.ndarray,
    raw: np.ndarray,
    rpeak_times: list[float],
    frozen_metrics: Dict[str, Any] | None = None,
) -> None:
    if len(t) < 2:
        return

    t0 = float(t[0])
    duration = max(0.001, float(t[-1] - t0))
    peak_indices = []
    for peak_time in rpeak_times:
        idx = int(np.argmin(np.abs(t - peak_time)))
        if 0 <= idx < len(t):
            peak_indices.append(idx)

    STATE.demo_loop = {
        "duration": duration,
        "filtered": filtered.astype(float).tolist(),
        "raw": raw.astype(float).tolist(),
        "peak_indices": peak_indices,
        "stored_at": time.time(),
        "frozen_metrics": frozen_metrics or {},
    }


def render_demo_loop() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[float]] | None:
    loop = STATE.demo_loop
    if not loop:
        return None

    filtered = np.asarray(loop.get("filtered") or [], dtype=float)
    raw = np.asarray(loop.get("raw") or [], dtype=float)
    peak_indices = [int(i) for i in (loop.get("peak_indices") or [])]
    duration = float(loop.get("duration") or 0)

    if len(filtered) < 2 or len(raw) != len(filtered) or duration <= 0:
        return None

    n = len(filtered)
    phase = int((time.monotonic() * 250.0) % n)
    filtered_loop = np.roll(filtered, -phase)
    raw_loop = np.roll(raw, -phase)

    t_end = time.monotonic()
    t_loop = np.linspace(t_end - duration, t_end, n)
    shifted_peak_indices = sorted(((idx - phase) % n for idx in peak_indices))
    rpeak_times = [float(t_loop[idx]) for idx in shifted_peak_indices]

    return t_loop, filtered_loop, raw_loop, rpeak_times


def compute_metrics_from_window(t: np.ndarray, v: np.ndarray, fs_in: Optional[float]) -> Dict[str, Any]:
    fs_use = fs_in or FS_TARGET
    metrics = process_window(t, v, fs=float(fs_use), thr_norm=THR_NORM)
    metrics.setdefault("snr_db", None)
    metrics.setdefault("artifacts_pct", None)
    metrics.setdefault("raw_rpeaks", metrics.get("rpeaks", 0))
    metrics.setdefault("analysis_duration_sec", round(float(t[-1] - t[0]), 2) if len(t) >= 2 else 0)
    metrics.setdefault("valid_rr_count", len(metrics.get("rr_s") or []))
    metrics.setdefault("metric_warnings", [])
    metrics.setdefault("quality", "unknown")
    metrics.setdefault("note", "")
    for warning in metrics.get("metric_warnings") or []:
        log_event("metric_warning", str(warning))
    return metrics


def build_interpretation(metrics: Dict[str, Any]) -> str:
    quality = metrics.get("quality")
    bpm = metrics.get("hr_median")

    if quality == "leads_off":
        return "Registro invalido por electrodos desconectados"
    if quality == "hw_error":
        return "Registro afectado por error de hardware"
    if bpm is None:
        return "Sin interpretacion automatica concluyente"
    if bpm < 60:
        return "Ritmo aparente bajo; requiere correlacion clinica"
    if bpm > 100:
        return "Ritmo aparente elevado; requiere correlacion clinica"
    return "Ritmo aparente dentro de rango; no constituye diagnostico medico"


def find_session_by_id(session_id: str) -> Optional[Dict[str, Any]]:
    items = list_sessions(DB_PATH, patient_id=None, limit=5000)
    for item in items:
        if item.get("session_id") == session_id:
            return item
    return None


def safe_pdf_text(value: Any) -> str:
    if value is None or value == "":
        return "--"
    return str(value)


def build_session_pdf_bytes(session_item: Dict[str, Any]) -> BytesIO:
    raw_metrics = session_item.get("metrics_json") or "{}"
    try:
        metrics = json.loads(raw_metrics)
    except Exception:
        metrics = {}

    buffer = BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    left = 16 * mm
    right = width - 16 * mm
    top = height - 16 * mm

    brand = HexColor("#0F172A")
    accent = HexColor("#0F766E")
    accent_soft = HexColor("#CCFBF1")
    border = HexColor("#CBD5E1")
    text_main = HexColor("#0F172A")
    text_muted = HexColor("#475569")
    logo_path = "/home/edcal2025/mi-landing/mi-proyecto-ecg/Frontend/Imagenes /Logo Medinic - Emorie.png"

    patient_name = metrics.get("patient_name", session_item.get("patient_id", ""))
    patient_id = metrics.get("patient_identifier", session_item.get("patient_id", ""))
    study_date = metrics.get("study_date", session_item.get("started_at_iso", "") or session_item.get("started_at", ""))
    try:
        study_date_fmt = datetime.fromisoformat(str(study_date)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        study_date_fmt = safe_pdf_text(study_date)
    bpm = safe_pdf_text(metrics.get("hr_median", ""))
    quality = safe_pdf_text(metrics.get("quality", ""))
    rmssd = safe_pdf_text(metrics.get("rmssd_ms", ""))
    sdnn = safe_pdf_text(metrics.get("sdnn_ms", ""))
    snr = safe_pdf_text(metrics.get("snr_db", ""))
    artifacts = safe_pdf_text(metrics.get("artifacts_pct", ""))
    record_id = safe_pdf_text(metrics.get("record_id", ""))
    duration = safe_pdf_text(metrics.get("duration", session_item.get("duration_sec", "")))

    clinical_img_path = None
    raw_record_id = metrics.get("record_id")
    if raw_record_id:
        candidate = Path("data") / "exports" / str(raw_record_id) / f"{raw_record_id}_clinical.png"
        if candidate.exists():
            clinical_img_path = candidate

    def draw_text(x, y, text, size=10, color=text_main, bold=False):
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, y, safe_pdf_text(text))

    def draw_right_text(x, y, text, size=10, color=text_main, bold=False):
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawRightString(x, y, safe_pdf_text(text))

    def draw_label_value(x, y, label, value, width_box=78 * mm):
        draw_text(x, y, label, size=8, color=text_muted, bold=True)
        draw_text(x, y - 5 * mm, value, size=10, color=text_main)
        c.setStrokeColor(border)
        c.line(x, y - 7 * mm, x + width_box, y - 7 * mm)

    def draw_metric_card(x, y, w, h, title, value, subtitle=None):
        c.setFillColor(colors.white)
        c.setStrokeColor(border)
        c.roundRect(x, y - h, w, h, 4 * mm, stroke=1, fill=1)
        draw_text(x + 4 * mm, y - 6 * mm, title, size=8, color=text_muted, bold=True)
        draw_text(x + 4 * mm, y - 15 * mm, value, size=18, color=brand, bold=True)
        if subtitle:
            draw_text(x + 4 * mm, y - 22 * mm, subtitle, size=8, color=text_muted)

    def draw_section_title(y, title):
        c.setFillColor(accent)
        c.roundRect(left, y - 5 * mm, 4 * mm, 4 * mm, 1 * mm, stroke=0, fill=1)
        draw_text(left + 7 * mm, y - 1 * mm, title, size=12, color=brand, bold=True)

    c.setTitle(f"Reporte ECG {session_item.get('session_id', '')}")

    c.setFillColor(brand)
    c.roundRect(left, top - 24 * mm, right - left, 22 * mm, 5 * mm, stroke=0, fill=1)

    if os.path.exists(logo_path):
        try:
            c.drawImage(ImageReader(logo_path), left + 4 * mm, top - 20 * mm, width=16 * mm, height=16 * mm, mask="auto")
        except Exception:
            pass

    draw_text(left + 24 * mm, top - 8 * mm, "REPORTE CLINICO DE MONITOREO ECG", size=13, color=colors.white, bold=True)
    draw_text(left + 24 * mm, top - 16 * mm, "Sistema Medinic ECG - Plataforma IoT de adquisicion y analisis", size=8.5, color=accent_soft)

    draw_right_text(right - 6 * mm, top - 8 * mm, "Sesion", size=8, color=accent_soft, bold=True)
    draw_right_text(right - 6 * mm, top - 16 * mm, session_item.get("session_id", ""), size=7.5, color=colors.white, bold=True)

    y = top - 32 * mm

    c.setFillColor(colors.white)
    c.setStrokeColor(border)
    c.roundRect(left, y - 36 * mm, right - left, 34 * mm, 5 * mm, stroke=1, fill=1)

    draw_text(left + 5 * mm, y - 7 * mm, "Resumen del estudio", size=12, color=brand, bold=True)
    draw_text(left + 5 * mm, y - 15 * mm, f"Paciente: {patient_name}", size=10)
    draw_text(left + 92 * mm, y - 15 * mm, f"Identificacion: {patient_id}", size=10)
    draw_text(left + 5 * mm, y - 23 * mm, f"Fecha del estudio: {study_date_fmt}", size=10)
    draw_text(left + 5 * mm, y - 31 * mm, f"Record ID: {record_id}", size=10)

    y -= 44 * mm

    card_w = (right - left - 12 * mm) / 4
    draw_metric_card(left, y, card_w, 22 * mm, "BPM", bpm)
    draw_metric_card(left + card_w + 4 * mm, y, card_w, 22 * mm, "Calidad", quality)
    draw_metric_card(left + (card_w + 4 * mm) * 2, y, card_w, 22 * mm, "RMSSD", rmssd, "ms")
    draw_metric_card(left + (card_w + 4 * mm) * 3, y, card_w, 22 * mm, "SDNN", sdnn, "ms")

    y -= 30 * mm

    draw_section_title(y, "Datos del paciente")
    y -= 8 * mm
    draw_label_value(left, y, "Paciente", patient_name)
    draw_label_value(left + 92 * mm, y, "Identificador", patient_id)
    y -= 12 * mm
    draw_label_value(left, y, "Edad", metrics.get("age", ""))
    draw_label_value(left + 92 * mm, y, "Sexo", metrics.get("sex", ""))
    y -= 18 * mm

    draw_section_title(y, "Datos del estudio")
    y -= 8 * mm
    draw_label_value(left, y, "Sesion", session_item.get("session_id", ""))
    draw_label_value(left + 92 * mm, y, "Fecha estudio", study_date)
    y -= 12 * mm
    draw_label_value(left, y, "Inicio", session_item.get("started_at_iso", "") or session_item.get("started_at", ""))
    draw_label_value(left + 92 * mm, y, "Fin", session_item.get("ended_at_iso", "") or session_item.get("stopped_at", ""))
    y -= 12 * mm
    draw_label_value(left, y, "Duracion", duration)
    draw_label_value(left + 92 * mm, y, "Lead", metrics.get("lead", REPORT_LEAD))
    y -= 12 * mm
    draw_label_value(left, y, "Velocidad", metrics.get("speed", REPORT_SPEED))
    draw_label_value(left + 92 * mm, y, "Ganancia", metrics.get("gain", REPORT_GAIN))
    y -= 18 * mm

    draw_section_title(y, "Metricas ECG y calidad de senal")
    y -= 8 * mm
    draw_label_value(left, y, "BPM", metrics.get("hr_median", ""))
    draw_label_value(left + 92 * mm, y, "Frecuencia cardiaca media", metrics.get("hr_mean", ""))
    y -= 12 * mm
    draw_label_value(left, y, "Picos R", metrics.get("rpeaks", ""))
    draw_label_value(left + 92 * mm, y, "Calidad", quality)
    y -= 12 * mm
    draw_label_value(left, y, "SNR (dB)", snr)
    draw_label_value(left + 92 * mm, y, "Artefactos (%)", artifacts)
    y -= 12 * mm
    draw_label_value(left, y, "Lead off", metrics.get("lead_off", ""))
    draw_label_value(left + 92 * mm, y, "Referencia ECG", "Sesion registrada")
    y -= 18 * mm

    clinical_img_path = None
    record_id_value = metrics.get("record_id")
    if record_id_value:
        clinical_candidate = Path("data") / "exports" / str(record_id_value) / f"{record_id_value}_clinical.png"
        if clinical_candidate.exists():
            clinical_img_path = clinical_candidate

    c.showPage()
    y = top - 20 * mm

    draw_section_title(y, "Sistema y hardware")
    y -= 8 * mm
    draw_label_value(left, y, "Dispositivo", metrics.get("device", SENSOR_NAME))
    draw_label_value(left + 92 * mm, y, "Gateway", metrics.get("gateway", GATEWAY_NAME))
    y -= 12 * mm
    draw_label_value(left, y, "Canal ADC", metrics.get("adc_channel", ADC_CHANNEL))
    draw_label_value(left + 92 * mm, y, "Data rate ADC", metrics.get("adc_data_rate", ADC_DATA_RATE))
    y -= 12 * mm
    draw_label_value(left, y, "Frecuencia estimada", metrics.get("fs_est", ""))
    draw_label_value(left + 92 * mm, y, "Estado hardware", metrics.get("hw_ok", ""))
    y -= 12 * mm
    draw_label_value(left, y, "Error hardware", safe_pdf_text(metrics.get("hw_error", ""))[:55])    
    y -= 18 * mm

    c.setStrokeColor(border)
    c.line(left, 18 * mm, right, 18 * mm)
    draw_text(left, 13 * mm, "Reporte generado automaticamente por Medinic ECG.", size=8, color=text_muted)
    draw_text(left, 9 * mm, "Este documento no sustituye la valoracion medica profesional.", size=8, color=text_muted)

    c.showPage()
    c.save()

    if clinical_img_path:
        c.showPage()
        y = top - 16 * mm
        draw_section_title(y, "Trazado clinico exportado")
        y -= 10 * mm

        c.setFillColor(colors.white)
        c.setStrokeColor(border)
        img_x = left
        img_y = 28 * mm
        img_w = right - left
        img_h = y - img_y

        c.roundRect(img_x, img_y, img_w, img_h, 5 * mm, stroke=1, fill=1)

        try:
            c.drawImage(
                ImageReader(str(clinical_img_path)),
                img_x + 4 * mm,
                img_y + 4 * mm,
                width=img_w - 8 * mm,
                height=img_h - 8 * mm,
                preserveAspectRatio=True,
                anchor='c',
                mask="auto",
            )
        except Exception:
            draw_text(img_x + 8 * mm, y - 10 * mm, "No se pudo incrustar la imagen clinica exportada", size=11, color=danger, bold=True)

    if clinical_img_path:
        c.showPage()
        page_top = height - 16 * mm

        draw_section_title(page_top - 2 * mm, "Trazado clinico exportado")

        c.setFillColor(colors.white)
        c.setStrokeColor(border)

        frame_x = left
        frame_y = 22 * mm
        frame_w = right - left
        frame_h = page_top - frame_y - 12 * mm

        c.roundRect(frame_x, frame_y, frame_w, frame_h, 5 * mm, stroke=1, fill=1)

        try:
            c.drawImage(
                ImageReader(str(clinical_img_path)),
                frame_x + 4 * mm,
                frame_y + 4 * mm,
                width=frame_w - 8 * mm,
                height=frame_h - 8 * mm,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
        except Exception:
            draw_text(
                frame_x + 8 * mm,
                page_top - 18 * mm,
                "No se pudo incrustar la imagen clinica exportada",
                size=11,
                color=danger,
                bold=True,
            )

    buffer.seek(0)
    return buffer


def acquisition_worker():
    log_event("acq_start")

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c, address=I2C_ADDRESS)
        ads.gain = 1
        ads.data_rate = ADC_DATA_RATE
        chan = AnalogIn(ads, ADC_CHANNEL)
        battery_chan = AnalogIn(ads, BATTERY_ADC_CHANNEL)

        STATE.hw_ok = True
        STATE.hw_error = ""
        with STATE.lock:
            STATE.last_metrics.update({
                "device": SENSOR_NAME,
                "gateway": GATEWAY_NAME,
                "hw_ok": True,
                "hw_error": "",
                "adc_channel": ADC_CHANNEL,
                "adc_data_rate": ADC_DATA_RATE,
                "battery_adc_channel": BATTERY_ADC_CHANNEL,
            })
    except Exception as e:
        STATE.hw_ok = False
        STATE.hw_error = str(e)
        with STATE.lock:
            STATE.last_metrics.update({
                "hw_ok": False,
                "hw_error": STATE.hw_error,
                "quality": "hw_error",
                "note": f"ADC init error: {STATE.hw_error}",
            })
        log_event("hw_error", str(e))
        return

    STATE.running = True
    t_start = time.perf_counter()
    STATE.wall_start = time.time()  # anchor to convert buf_t (monotonic) to wall-clock, used by ws_ecg
    t_last_metrics = 0.0
    lead_off_count = 0
    lead_on_count = 0

    while STATE.running:
        now = time.perf_counter() - t_start

        try:
            val = float(chan.voltage)
        except OSError as e:
            STATE.hw_ok = False
            STATE.hw_error = f"I2C read error: {e}"
            STATE.last_hw_error = STATE.hw_error
            with STATE.lock:
                STATE.last_metrics.update({
                    "hw_ok": False,
                    "hw_error": STATE.hw_error,
                    "last_hw_error": STATE.last_hw_error,
                    "quality": "hw_error",
                    "note": "I2C/ADC error; retrying",
                })
            time.sleep(0.2)
            continue

        with STATE.lock:
            STATE.buf_t.append(now)
            STATE.buf_v.append(val)
            while STATE.buf_t and (STATE.buf_t[-1] - STATE.buf_t[0]) > BUFFER_S:
                STATE.buf_t.popleft()
                STATE.buf_v.popleft()
        _diag_log_sample(now)

        if now - t_last_metrics >= UPDATE_EVERY_S:
            t_last_metrics = now

            lo = {"lead_off": None, "lo_plus": None, "lo_minus": None}
            sdn_state: Optional[bool] = None
            lead_off_confirmed = False

            with STATE.lock:
                session_recording = bool(STATE.recording)

            if session_recording:
                try:
                    lo = read_lead_off()
                    if lo["lead_off"]:
                        lead_off_count += 1
                        lead_on_count = 0
                    else:
                        lead_on_count += 1
                        lead_off_count = 0

                    lead_off_confirmed = lead_off_count >= LEAD_OFF_DEBOUNCE_N
                    lead_on_confirmed = lead_on_count >= LEAD_OFF_DEBOUNCE_N

                    if AUTO_SHUTDOWN_ON_LEAD_OFF and lead_off_confirmed:
                        set_sdn(False)
                        sdn_state = False
                    elif lead_on_confirmed:
                        set_sdn(True)
                        sdn_state = True
                    else:
                        sdn_state = bool(GPIO.input(GPIO_SDN))
                except Exception as e:
                    log_event("lead_off_error", str(e))
            else:
                lead_off_count = 0
                lead_on_count = 0

            with STATE.lock:
                t_arr = np.array(STATE.buf_t, dtype=float)
                v_arr = np.array(STATE.buf_v, dtype=float)
                current_context = dict(STATE.current_record_context)

            fs_est = estimate_fs(t_arr)

            if len(t_arr) > 0:
                t1 = t_arr[-1]
                mask = t_arr >= (t1 - WINDOW_S)
                t_win = t_arr[mask]
                v_win_raw = v_arr[mask]
            else:
                t_win = t_arr
                v_win_raw = v_arr

            # process_window owns the unified MAD filtering/detection pipeline.
            v_win = v_win_raw

            if lead_off_confirmed:
                metrics = {
                    "hr_median": None,
                    "hr_mean": None,
                    "rpeaks": 0,
                    "raw_rpeaks": 0,
                    "analysis_duration_sec": round(float(t_win[-1] - t_win[0]), 2) if len(t_win) >= 2 else 0,
                    "valid_rr_count": 0,
                    "quality": "leads_off",
                    "note": "electrodes disconnected",
                    "rr_s": [],
                    "sdnn_ms": None,
                    "rmssd_ms": None,
                    "pnn50": None,
                    "metric_warnings": [],
                    "snr_db": None,
                    "artifacts_pct": None,
                }
            else:
                metrics = compute_metrics_from_window(t_win, v_win, fs_est)

            battery_metrics = read_battery_payload(battery_chan)
            interpretation = build_interpretation(metrics)

            with STATE.lock:
                STATE.last_metrics.update({
                    **current_context,
                    "device": SENSOR_NAME,
                    "gateway": GATEWAY_NAME,
                    "ts": time.time(),
                    "fs_est": fs_est,
                    "hw_ok": STATE.hw_ok,
                    "hw_error": STATE.hw_error,
                    "last_hw_error": STATE.last_hw_error,
                    "adc_channel": ADC_CHANNEL,
                    "adc_data_rate": ADC_DATA_RATE,
                    "clients": STATE.clients,
                    "interpretation": interpretation,
                    "lead_off": lo["lead_off"],
                    "lo_plus": lo["lo_plus"],
                    "lo_minus": lo["lo_minus"],
                    "sdn": sdn_state,
                    "signal_mode": "filtered",
                    **metrics,
                    **battery_metrics,
                })

        time.sleep(0.002)


def start_acquisition():
    if STATE.running:
        return
    threading.Thread(target=acquisition_worker, daemon=True).start()


app = FastAPI(title="ECG IoT Backend", version="0.8.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

init_db(DB_PATH)
init_sessions_db(DB_PATH)
init_record_sequence_db()


@app.get("/")
def root():
    return {"ok": True, "service": "ECG IoT Backend", "device": SENSOR_NAME, "gateway": GATEWAY_NAME}


@app.get("/users/me")
def current_user(request: Request):
    user = require_api_key(request)
    return public_user_payload(user)


@app.get("/system/status")
def system_status(request: Request):
    require_api_key(request)
    return get_system_status_payload()


@app.get("/health")
def health():
    with STATE.lock:
        metrics = dict(STATE.last_metrics)

    return {
        "ok": True,
        "device": SENSOR_NAME,
        "gateway": GATEWAY_NAME,
        "hw_ok": STATE.hw_ok,
        "hw_error": STATE.hw_error,
        "adc_channel": ADC_CHANNEL,
        "adc_data_rate": ADC_DATA_RATE,
        "clients": STATE.clients,
        "fs_est": metrics.get("fs_est"),
        "lead_off": metrics.get("lead_off"),
        "quality": metrics.get("quality"),
        "record_id": metrics.get("record_id"),
        "battery_pct": metrics.get("battery_pct"),
        "battery_voltage_v": metrics.get("battery_voltage_v"),
        "battery_adc_voltage_v": metrics.get("battery_adc_voltage_v"),
    }


@app.on_event("startup")
def on_startup():
    log_event("startup")
    try:
        gpio_setup()
    except Exception as e:
        log_event("gpio_error", str(e))
    start_acquisition()


@app.on_event("shutdown")
def on_shutdown():
    STATE.running = False
    try:
        GPIO.cleanup()
    except Exception:
        pass


@app.websocket("/ws/ecg")
async def ws_ecg(websocket: WebSocket):
    try:
        api_key = websocket.query_params.get("api_key", "")
        if api_key:
            get_api_user_from_key(api_key)
        else:
            get_user_from_credentials(
                websocket.query_params.get("username", ""),
                websocket.query_params.get("password", ""),
            )
    except HTTPException:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    with STATE.lock:
        STATE.clients += 1
        STATE.last_metrics["clients"] = STATE.clients

    seq = 0  # per-connection counter: resets on reconnect, so a client-side reset is itself
             # a reconnection event; a gap > 1 within a connection flags a missed/delayed tick

    try:
        while True:
            await asyncio.sleep(0.1)

            with STATE.lock:
                metrics = dict(STATE.last_metrics)
                t_arr = np.array(STATE.buf_t, dtype=float)
                v_arr = np.array(STATE.buf_v, dtype=float)
                wall_start = STATE.wall_start

            t_last = None
            if len(t_arr) > 0:
                t_last = t_arr[-1]
                mask = t_arr >= (t_last - 10.0)
                t2 = t_arr[mask]
                v2_raw = v_arr[mask]

                fs_stream = estimate_fs(t2) or metrics.get("fs_est") or FS_TARGET
                t2_display, v2_filtered, rpeak_times = prepare_monitor_signal(t2, v2_raw, fs_stream)
                raw_display = np.interp(t2_display, t2, v2_raw) if len(t2) > 1 else v2_raw
                t2 = t2_display
                use_demo_loop = False
                frozen_metrics = {}

                if is_stable_monitor_window(v2_filtered, rpeak_times, metrics):
                    with STATE.lock:
                        store_demo_loop(
                            t2,
                            v2_filtered,
                            raw_display,
                            rpeak_times,
                            frozen_metrics=build_demo_frozen_metrics(metrics, rpeak_times),
                        )

                if DEMO_LOOP_ENABLED and STATE.demo_loop is not None:
                    with STATE.lock:
                        demo_payload = render_demo_loop()
                        frozen_metrics = dict((STATE.demo_loop or {}).get("frozen_metrics") or {})
                    if demo_payload is not None:
                        t2, v2_filtered, raw_display, rpeak_times = demo_payload
                        use_demo_loop = True

                max_pts = 2000
                if len(t2) > max_pts:
                    indices = np.linspace(0, len(t2) - 1, max_pts).astype(int)
                    t2 = t2[indices]
                    raw_display = raw_display[indices]
                    v2_filtered = v2_filtered[indices]
            else:
                t2 = np.array([])
                raw_display = np.array([])
                v2_filtered = np.array([])
                rpeak_times = []
                use_demo_loop = False
                frozen_metrics = {}

            if use_demo_loop:
                for key in (
                    "hr_median",
                    "hr_mean",
                    "rpeaks",
                    "raw_rpeaks",
                    "analysis_duration_sec",
                    "valid_rr_count",
                    "rmssd_ms",
                    "sdnn_ms",
                    "pnn50",
                    "snr_db",
                    "artifacts_pct",
                    "quality",
                    "diagnosis",
                    "confidence",
                    "metric_warnings",
                ):
                    if key in frozen_metrics:
                        metrics[key] = frozen_metrics[key]

            metrics["rpeak_times"] = rpeak_times
            metrics["display_fs"] = 250.0
            metrics["display_filter"] = "resample_250hz_butterworth2_0.5_40hz_mad_k8"
            metrics["display_detector"] = "mad"
            metrics["display_detector_k"] = MAD_K
            metrics["demo_loop"] = use_demo_loop

            # Latency/jitter/packet-loss instrumentation (see pi_diagnostics/RUNBOOK.md):
            # seq resets to 0 on reconnect; sample_acquired_at is the last raw sample in this
            # tick's buffer, converted from the acquisition thread's monotonic clock to wall
            # time via wall_start (captured at the same instant as that thread's t_start), so
            # it is directly comparable to server_sent_at without a separate clock-sync step.
            sample_acquired_at = (wall_start + float(t_last)) if (t_last is not None and wall_start) else None
            await websocket.send_json({
                "device": SENSOR_NAME,
                "gateway": GATEWAY_NAME,
                "seq": seq,
                "server_sent_at": time.time(),
                "sample_acquired_at": sample_acquired_at,
                "metrics": metrics,
                "samples": {
                    "t": t2.tolist(),
                    "v": v2_filtered.tolist(),
                    "raw_v": raw_display.tolist(),
                },
            })
            seq += 1
    except WebSocketDisconnect:
        pass
    finally:
        with STATE.lock:
            STATE.clients = max(0, STATE.clients - 1)
            STATE.last_metrics["clients"] = STATE.clients


class PatientIn(BaseModel):
    patient_id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=80)
    sex: str = Field(..., min_length=1, max_length=1)
    age: int = Field(..., ge=0, le=120)


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=120)


@app.post("/auth/login")
def login(body: LoginIn):
    return get_user_from_credentials(body.username, body.password)


@app.post("/patients")
def create_or_update_patient(body: PatientIn, request: Request):
    require_write_access(request)
    return upsert_patient(
        DB_PATH,
        patient_id=body.patient_id.strip(),
        display_name=body.display_name.strip(),
        sex=body.sex.strip().upper(),
        age=int(body.age),
    )


@app.get("/patients")
def patients(request: Request, limit: int = 50):
    require_api_key(request)
    return {"items": list_patients(DB_PATH, limit=limit)}


@app.get("/patients/{patient_id}")
def patient_by_id(patient_id: str, request: Request):
    require_api_key(request)
    p = get_patient(DB_PATH, patient_id=patient_id)
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


class SessionStartIn(BaseModel):
    patient_id: str = Field(..., min_length=1, max_length=64)
    patient_name: Optional[str] = Field(default=None, max_length=80)
    age: Optional[int] = Field(default=None, ge=0, le=120)
    sex: Optional[str] = Field(default=None, min_length=1, max_length=1)
    note: str = Field(default="", max_length=200)




def trigger_session_export(record_id: str | None) -> None:
    if not record_id:
        return

    def _worker():
        try:
            backend_dir = Path(__file__).resolve().parent
            script_path = backend_dir / "export_physionet_style.py"
            if not script_path.exists():
                print(f"[export] Script no encontrado: {script_path}")
                return

            subprocess.run(
                [sys.executable, str(script_path), record_id],
                cwd=str(backend_dir),
                check=True,
                timeout=180,
            )
            print(f"[export] Exportacion automatica completada para {record_id}")
        except Exception as e:
            print(f"[export] Error exportando {record_id}: {e}")

    threading.Thread(target=_worker, daemon=True).start()


@app.post("/sessions/start")
def api_start_session(body: SessionStartIn, request: Request):
    require_write_access(request)

    patient_id = body.patient_id.strip()
    patient = get_patient(DB_PATH, patient_id=patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    age = body.age if body.age is not None else patient.get("age")
    sex = body.sex.strip().upper() if body.sex else (patient.get("sex") or "").upper()
    patient_name = body.patient_name.strip() if body.patient_name else patient.get("display_name", patient_id)

    if age is None or not sex:
        raise HTTPException(status_code=400, detail="Age and sex are required")

    record_id = next_record_id()
    session_id = f"sess_{uuid.uuid4().hex}"
    study_date = datetime.now().isoformat()

    with STATE.lock:
        STATE.recording = True
        STATE.last_good_metrics = {}
        STATE.demo_loop = None
        STATE.current_record_context = {
            "record_id": record_id,
            "patient_name": patient_name,
            "patient_identifier": patient_id,
            "age": int(age),
            "sex": sex,
            "lead": REPORT_LEAD,
            "study_date": study_date,
            "speed": REPORT_SPEED,
            "gain": REPORT_GAIN,
            "duration": None,
            "interpretation": None,
            "ecg_file_reference": None,
        }
        STATE.last_metrics.update(STATE.current_record_context)
        metrics_to_persist = dict(STATE.last_good_metrics) if STATE.last_good_metrics else dict(STATE.last_metrics)

    result = start_session(DB_PATH, session_id=session_id, patient_id=patient_id, note=body.note.strip())
    result["record_id"] = record_id
    return result


class SessionStopIn(BaseModel):
    duration_sec: float = Field(..., ge=0)
    note: str = Field(default="", max_length=200)


@app.post("/sessions/stop/{session_id}")
def api_stop_session(session_id: str, body: SessionStopIn, request: Request):
    require_write_access(request)

    with STATE.lock:
        metrics = dict(STATE.last_metrics)
        metrics["duration"] = float(body.duration_sec)
        metrics["ecg_file_reference"] = f"session:{session_id}"
        metrics["interpretation"] = build_interpretation(metrics)
        STATE.last_metrics.update({
            "duration": metrics["duration"],
            "ecg_file_reference": metrics["ecg_file_reference"],
            "interpretation": metrics["interpretation"],
        })
        metrics_to_persist = dict(STATE.last_good_metrics) if STATE.last_good_metrics else dict(STATE.last_metrics)
        record_id_to_export = metrics_to_persist.get("record_id") or STATE.current_record_context.get("record_id")

        STATE.recording = False
        STATE.current_record_context = {}
        STATE.last_good_metrics = {}
        trigger_session_export(record_id_to_export)

    metrics_json = json.dumps(metrics_to_persist, ensure_ascii=False)

    try:
        return stop_session(
            DB_PATH,
            session_id=session_id,
            duration_sec=float(body.duration_sec),
            metrics_json=metrics_json,
            note=body.note.strip(),
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")


@app.get("/sessions")
def api_list_sessions(request: Request, patient_id: str | None = None, limit: int = 50):
    require_api_key(request)
    return {"items": list_sessions(DB_PATH, patient_id=patient_id, limit=limit)}


@app.get("/sessions/export.xlsx")
def export_sessions_xlsx(request: Request, patient_id: str | None = None, limit: int = 200):
    require_api_key(request)
    items = list_sessions(DB_PATH, patient_id=patient_id, limit=limit)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sesiones ECG"

    ws.append([
        "recordId",
        "session_id",
        "patientName",
        "patientIdentifier",
        "age",
        "sex",
        "bpm",
        "signalQuality",
        "lead",
        "studyDate",
        "speed",
        "gain",
        "duration",
        "interpretation",
        "ecgFileReference",
        "started_at",
        "stopped_at",
        "hr_mean",
        "rpeaks",
        "sdnn_ms",
        "rmssd_ms",
        "pnn50",
        "snr_db",
        "artifacts_pct",
        "lead_off",
        "device",
        "gateway",
        "hw_ok",
        "hw_error",
    ])

    for item in items:
        raw_metrics = item.get("metrics_json") or "{}"
        try:
            metrics = json.loads(raw_metrics)
        except Exception:
            metrics = {}

        ws.append([
            metrics.get("record_id", ""),
            item.get("session_id", ""),
            metrics.get("patient_name", ""),
            metrics.get("patient_identifier", item.get("patient_id", "")),
            metrics.get("age", ""),
            metrics.get("sex", ""),
            metrics.get("hr_median", ""),
            metrics.get("quality", ""),
            metrics.get("lead", REPORT_LEAD),
            metrics.get("study_date", item.get("started_at_iso", "") or item.get("started_at", "")),
            metrics.get("speed", REPORT_SPEED),
            metrics.get("gain", REPORT_GAIN),
            metrics.get("duration", item.get("duration_sec", "")),
            metrics.get("interpretation", ""),
            metrics.get("ecg_file_reference", f"session:{item.get('session_id', '')}"),
            item.get("started_at_iso", "") or item.get("started_at", ""),
            item.get("ended_at_iso", "") or item.get("stopped_at", ""),
            metrics.get("hr_mean", ""),
            metrics.get("rpeaks", ""),
            metrics.get("sdnn_ms", ""),
            metrics.get("rmssd_ms", ""),
            metrics.get("pnn50", ""),
            metrics.get("snr_db", ""),
            metrics.get("artifacts_pct", ""),
            metrics.get("lead_off", ""),
            metrics.get("device", ""),
            metrics.get("gateway", ""),
            metrics.get("hw_ok", ""),
            metrics.get("hw_error", ""),
        ])

    for column_cells in ws.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter
        for cell in column_cells:
            cell_value = "" if cell.value is None else str(cell.value)
            max_length = max(max_length, len(cell_value))
        ws.column_dimensions[column_letter].width = min(max_length + 2, 40)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sessions_export.xlsx"},
    )


@app.get("/sessions/report.pdf/{session_id}")
def export_session_pdf(session_id: str, request: Request):
    require_api_key(request)

    session_item = find_session_by_id(session_id)
    if not session_item:
        raise HTTPException(status_code=404, detail="Session not found")

    pdf_buffer = build_session_pdf_bytes(session_item)

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={session_id}_report.pdf"},
    )


# --- Exportacion de sesiones estilo PhysioNet ---
def get_session_by_id_for_export(session_id: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def safe_export_filename(value: Any) -> str:
    value = str(value or "ECG-EXPORT")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def estimate_export_annotations(metrics: Dict[str, Any], fs: float, total_samples: int) -> list[tuple[int, float, str, str]]:
    rr_s = metrics.get("rr_s") or []
    annotations: list[tuple[int, float, str, str]] = []

    if rr_s:
        t = 0.4
        annotations.append((int(round(t * fs)), t, "N", "R peak estimado"))
        for rr in rr_s:
            try:
                t += float(rr)
            except Exception:
                continue
            sample = int(round(t * fs))
            if 0 <= sample < total_samples:
                annotations.append((sample, t, "N", "R peak estimado desde RR"))
        return annotations

    rpeaks = int(metrics.get("rpeaks") or 0)
    bpm = float(metrics.get("hr_median") or metrics.get("hr_mean") or 0)
    if rpeaks > 0 and bpm > 0:
        rr = 60.0 / bpm
        t = 0.4
        for _ in range(rpeaks):
            sample = int(round(t * fs))
            if 0 <= sample < total_samples:
                annotations.append((sample, t, "N", "R peak estimado"))
            t += rr

    return annotations


def csv_bytes(rows: list[list[Any]]) -> bytes:
    out = StringIO()
    writer = csv.writer(out)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _export_plot_signal(signal_values: list[Any], fs: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Returns (t, y_mv, y_v, peaks).

    y_mv is filtered and peaks are detected in non-overlapping WINDOW_S (10 s) tiles via
    windowed_mad_pipeline, matching the metrics and monitor paths instead of running the
    MAD threshold once over the whole exported session (see VERIFICACION_INTEGRACION_MAD.md).
    """
    y_v = np.asarray(signal_values, dtype=float)
    if y_v.size < 2:
        raise HTTPException(status_code=404, detail="La sesion no tiene senal suficiente para graficar.")

    t = np.arange(y_v.size, dtype=float) / max(fs, 1.0)
    y_raw_mv = (y_v - float(np.median(y_v))) * 1000.0

    y_mv, peaks = y_raw_mv, np.array([], dtype=int)
    if scipy_signal is not None and y_raw_mv.size > int(fs * 2):
        try:
            y_mv, peaks = windowed_mad_pipeline(y_raw_mv, fs, WINDOW_S)
        except Exception:
            pass

    return t, y_mv, y_v, peaks


def _add_ecg_grid(ax, duration_s: float, y_min: float, y_max: float) -> None:
    ax.set_xlim(0, duration_s)
    ax.set_ylim(y_min, y_max)

    # Papel ECG: a 25 mm/s, 1 cuadro pequeno = 0.04 s; 1 cuadro grande = 0.20 s.
    ax.set_xticks(np.arange(0, duration_s + 0.001, 0.20))
    ax.set_xticks(np.arange(0, duration_s + 0.001, 0.04), minor=True)
    ax.set_yticks(np.arange(np.floor(y_min), np.ceil(y_max) + 0.001, 0.5))
    ax.set_yticks(np.arange(np.floor(y_min), np.ceil(y_max) + 0.001, 0.1), minor=True)

    ax.grid(which="minor", color="#ffd6dc", linewidth=0.35, alpha=0.75)
    ax.grid(which="major", color="#f49aaa", linewidth=0.85, alpha=0.85)
    ax.tick_params(axis="both", which="both", length=0, labelsize=8, colors="#334155")
    for spine in ax.spines.values():
        spine.set_color("#cbd5e1")


def build_clinical_png_bytes(signal_values: list[Any], fs: float, record_id: str, metrics: Dict[str, Any]) -> BytesIO:
    t, y_mv, _, peaks = _export_plot_signal(signal_values, fs)
    duration = float(t[-1] - t[0]) if t.size > 1 else 0.0
    window_s = min(10.0, max(2.0, duration))
    n_window = max(2, int(window_s * fs))

    if peaks.size:
        center = int(peaks[len(peaks) // 2])
        start = max(0, min(center - n_window // 2, len(y_mv) - n_window))
    else:
        start = 0
    end = min(len(y_mv), start + n_window)

    tw = t[start:end] - t[start]
    yw = y_mv[start:end]
    local_peaks = peaks[(peaks >= start) & (peaks < end)] - start

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(14, 5.2), dpi=180)
    ax.set_facecolor("#fffafa")
    fig.patch.set_facecolor("white")
    _add_ecg_grid(ax, float(tw[-1]) if tw.size else window_s, -1.6, 1.6)

    ax.plot(tw, yw, color="#075985", linewidth=1.5, label="ECG filtrado")
    if local_peaks.size:
        ax.scatter(tw[local_peaks], yw[local_peaks], s=34, color="#dc2626", edgecolor="white", linewidth=0.9, zorder=5, label="Picos R")

    bpm = metrics.get("hr_median")
    bpm_txt = f"{float(bpm):.0f} BPM" if isinstance(bpm, (int, float)) else "-- BPM"
    ax.set_title(f"{record_id} | Trazado clinico filtrado | {bpm_txt}", fontsize=13, fontweight="bold", color="#0f172a")
    ax.set_xlabel("Tiempo (s) | 25 mm/s", fontsize=9, color="#334155")
    ax.set_ylabel("Amplitud visual (mV) | 10 mm/mV", fontsize=9, color="#334155")
    ax.legend(loc="upper right", fontsize=8, frameon=True)
    ax.text(0.01, 0.04, "Visualizacion centrada y escalada para lectura morfologica; datos crudos en .dat/.json",
            transform=ax.transAxes, fontsize=7.5, color="#475569")

    out = BytesIO()
    fig.tight_layout()
    fig.savefig(out, format="png", bbox_inches="tight")
    plt.close(fig)
    out.seek(0)
    return out


def build_qrs_zoom_png_bytes(signal_values: list[Any], fs: float, record_id: str) -> BytesIO:
    t, y_mv, _, peaks = _export_plot_signal(signal_values, fs)
    window_s = 3.0
    n_window = max(2, int(window_s * fs))

    if peaks.size:
        center = int(peaks[len(peaks) // 2])
        start = max(0, min(center - n_window // 2, len(y_mv) - n_window))
    else:
        start = 0
    end = min(len(y_mv), start + n_window)
    tw = t[start:end] - t[start]
    yw = y_mv[start:end]
    local_peaks = peaks[(peaks >= start) & (peaks < end)] - start

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10.5, 4.8), dpi=180)
    ax.set_facecolor("#fffafa")
    fig.patch.set_facecolor("white")
    _add_ecg_grid(ax, float(tw[-1]) if tw.size else window_s, -1.6, 1.6)

    ax.plot(tw, yw, color="#0f766e", linewidth=1.8)
    if local_peaks.size:
        ax.scatter(tw[local_peaks], yw[local_peaks], s=42, color="#ef4444", edgecolor="white", linewidth=1.0, zorder=5)

    ax.set_title(f"{record_id} | Zoom de complejos QRS", fontsize=12, fontweight="bold", color="#0f172a")
    ax.set_xlabel("Tiempo (s)", fontsize=9, color="#334155")
    ax.set_ylabel("mV visual", fontsize=9, color="#334155")

    out = BytesIO()
    fig.tight_layout()
    fig.savefig(out, format="png", bbox_inches="tight")
    plt.close(fig)
    out.seek(0)
    return out


def build_session_export_zip_bytes(session_item: Dict[str, Any]) -> tuple[BytesIO, str]:
    raw_metrics = session_item.get("metrics_json") or "{}"
    try:
        metrics = json.loads(raw_metrics)
    except Exception:
        metrics = {}

    record_id = safe_export_filename(metrics.get("record_id") or session_item.get("session_id"))
    fs = float(metrics.get("fs_est") or 0) or 1.0
    signal = metrics.get("v_clean") or []

    if not signal:
        raise HTTPException(status_code=404, detail="La sesion no tiene senal exportable.")

    dat_rows = [["sample", "time_s", "filtered_voltage_v", "filtered_voltage_mv"]]
    for i, value in enumerate(signal):
        value = float(value)
        dat_rows.append([i, f"{i / fs:.6f}", f"{value:.10f}", f"{value * 1000.0:.6f}"])

    duration_s = len(signal) / fs if fs > 0 else 0
    hea_text = "\n".join([
        f"{record_id} 1 {fs:.6f} {len(signal)}",
        f"{record_id}.dat 16 1000/mV 16 0 0 0 0 Lead_I",
        f"# session_id: {session_item.get('session_id')}",
        f"# patient_id: {session_item.get('patient_id')}",
        f"# patient_name: {metrics.get('patient_name', '')}",
        f"# age: {metrics.get('age', '')}",
        f"# sex: {metrics.get('sex', '')}",
        f"# started_at_iso: {session_item.get('started_at_iso')}",
        f"# ended_at_iso: {session_item.get('ended_at_iso')}",
        f"# duration_sec_session: {session_item.get('duration_sec')}",
        f"# duration_sec_exported_signal: {duration_s:.3f}",
        f"# bpm: {metrics.get('hr_median')}",
        f"# hr_mean: {metrics.get('hr_mean')}",
        f"# rpeaks: {metrics.get('rpeaks')}",
        f"# quality: {metrics.get('quality')}",
        f"# lead_off: {metrics.get('lead_off')}",
        "# note: Exportacion estilo PhysioNet generada por Medinic ECG.",
        "# note: El archivo .dat es CSV legible, no binario WFDB.",
        "",
    ]).encode("utf-8")

    atr_rows = [["sample", "time_s", "symbol", "description"]]
    for sample, t, symbol, desc in estimate_export_annotations(metrics, fs, len(signal)):
        atr_rows.append([sample, f"{t:.6f}", symbol, desc])

    json_payload = json.dumps(
        {
            "session": session_item,
            "metrics": metrics,
            "export_note": "Estructura estilo PhysioNet: .dat senal, .hea metadatos, .atr anotaciones.",
        },
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{record_id}.dat", csv_bytes(dat_rows))
        z.writestr(f"{record_id}.hea", hea_text)
        z.writestr(f"{record_id}.atr", csv_bytes(atr_rows))
        z.writestr(f"{record_id}.json", json_payload)
        try:
            clinical_png = build_clinical_png_bytes(signal, fs, record_id, metrics)
            z.writestr(f"{record_id}_clinical.png", clinical_png.getvalue())
        except Exception as e:
            LOGGER.warning("No se pudo generar clinical.png para %s: %s", record_id, e)
        try:
            qrs_png = build_qrs_zoom_png_bytes(signal, fs, record_id)
            z.writestr(f"{record_id}_qrs_zoom.png", qrs_png.getvalue())
        except Exception as e:
            LOGGER.warning("No se pudo generar qrs_zoom.png para %s: %s", record_id, e)

    buffer.seek(0)
    return buffer, record_id


@app.get("/sessions/export.zip/{session_id}")
def download_session_export_zip(session_id: str, request: Request):
    require_api_key(request)

    session_item = get_session_by_id_for_export(session_id)
    if not session_item:
        raise HTTPException(status_code=404, detail="Sesion no encontrada")

    buffer, record_id = build_session_export_zip_bytes(session_item)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{record_id}.zip"'},
    )
