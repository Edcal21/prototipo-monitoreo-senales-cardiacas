import React, { useEffect, useMemo, useRef, useState } from "react";
import { Activity, ArrowLeft, Heart, Plug, Power, Signal, User, Zap, Bell, Camera, FileText, Download } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

type Metrics = {
  record_id?: string | null;
  patient_name?: string | null;
  patient_identifier?: string | null;
  age?: number | null;
  sex?: string | null;
  lead?: string | null;
  study_date?: string | null;
  speed?: string | null;
  gain?: string | null;
  duration?: number | null;
  interpretation?: string | null;
  ecg_file_reference?: string | null;

  hr_median?: number | null;
  hr_mean?: number | null;
  rpeaks?: number | null;
  raw_rpeaks?: number | null;
  analysis_duration_sec?: number | null;
  valid_rr_count?: number | null;
  fs_est?: number | null;
  rmssd_ms?: number | null;
  sdnn_ms?: number | null;
  pnn50?: number | null;
  quality?: string | null;
  diagnosis?: string | null;
  confidence?: number | null;
  note?: string | null;
  battery_pct?: number | null;
  battery_voltage_v?: number | null;
  battery_adc_voltage_v?: number | null;

  lead_off?: boolean | null;
  lo_plus?: boolean | null;
  lo_minus?: boolean | null;
  sdn?: boolean | null;

  snr_db?: number | null;
  artifacts_pct?: number | null;
  metric_warnings?: string[] | null;

  ts?: number | null;
  device?: string | null;
  gateway?: string | null;
  hw_ok?: boolean | null;
  hw_error?: string | null;
  adc_channel?: number | null;
  adc_data_rate?: number | null;
  clients?: number | null;
  signal_mode?: string | null;
  rpeak_times?: number[] | null;
  display_fs?: number | null;
  display_filter?: string | null;
  demo_loop?: boolean | null;
};

type Samples = {
  t?: number[];
  v?: number[];
  raw_v?: number[];
};

type Payload = {
  device?: string | null;
  gateway?: string | null;
  metrics: Metrics;
  samples: Samples;
};

type AlertItem = {
  id: number;
  message: string;
  time: string;
  type: "warning" | "info" | "error";
};

type ConnectionState = "disconnected" | "connecting" | "connected";
type SignalViewMode = "filtered" | "raw";
type TimeWindowSec = 2 | 5 | 10;
type LastValidCards = {
  hr: number | null;
  rmssd: number | null;
  fs: number | null;
  rpeaks: number | null;
};

type BatterySnapshot = {
  pct: number | null;
  voltage: number | null;
  adcVoltage: number | null;
};

type SystemStatus = {
  cpu_percent?: number;
  ram_percent?: number;
  disk_percent?: number;
  temperature_c?: number | null;
  uptime_s?: number | null;
  backend_ok?: boolean;
  adc_ok?: boolean;
  adc_error?: string;
  clients?: number;
};

type SessionItem = {
  session_id: string;
  patient_id?: string;
  started_at?: string;
  started_at_iso?: string;
  stopped_at?: string;
  ended_at_iso?: string;
  duration_sec?: number;
  note?: string;
  metrics_json?: string;
};

const API_BASE = `http://${window.location.hostname}:8000`;
const PATIENT_ID = "MED-2025-001";
const SPEED_LABEL = "25 mm/s";
const GAIN_LABEL = "10 mm/mV";
const LEAD_LABEL = "Lead I";
const BATTERY_DISPLAY_UPDATE_MS = 60_000;

function fmtBool(v: boolean | null | undefined) {
  if (v === true) return "1";
  if (v === false) return "0";
  return "--";
}

function formatUptime(seconds?: number | null): string {
  if (seconds == null || Number.isNaN(seconds)) return "--";
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

function formatDateTime(value?: string) {
  if (!value) return "--";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString("es-ES", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function parseSessionMetrics(metricsJson?: string): Metrics {
  if (!metricsJson) return {};
  try {
    return JSON.parse(metricsJson) as Metrics;
  } catch {
    return {};
  }
}

function getSystemTone(
  value: number | null | undefined,
  warning: number,
  danger: number,
): "good" | "warning" | "danger" | "unknown" {
  if (value == null || Number.isNaN(value)) return "unknown";
  if (value >= danger) return "danger";
  if (value >= warning) return "warning";
  return "good";
}

function getToneClasses(tone: "good" | "warning" | "danger" | "unknown") {
  if (tone === "good") {
    return {
      box: "border-emerald-500/25 bg-emerald-500/8",
      value: "text-emerald-300",
    };
  }
  if (tone === "warning") {
    return {
      box: "border-amber-500/25 bg-amber-500/8",
      value: "text-amber-300",
    };
  }
  if (tone === "danger") {
    return {
      box: "border-red-500/25 bg-red-500/8",
      value: "text-red-300",
    };
  }
  return {
    box: "border-slate-800 bg-slate-950/40",
    value: "text-white",
  };
}

function getPercentile(values: number[], percentile: number) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.floor((sorted.length - 1) * percentile)));
  return sorted[index];
}

export function ECGMonitor({ onBack }: { onBack: () => void }) {
  const { logout, authHeaders, credentials, user } = useAuth();
  const canRecordEcg = user?.can_record_ecg !== false;

  const [isConnected, setIsConnected] = useState(false);
  const [data, setData] = useState<Payload>({
    device: null,
    gateway: null,
    metrics: {},
    samples: { t: [], v: [], raw_v: [] },
  });

  const [patientName, setPatientName] = useState("Paciente Demo");
  const [patientAge, setPatientAge] = useState("");
  const [patientSex, setPatientSex] = useState("");
  const [currentRecordId, setCurrentRecordId] = useState<string>("--");

  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [recordings, setRecordings] = useState(0);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionHistory, setSessionHistory] = useState<SessionItem[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [showAlerts, setShowAlerts] = useState(false);
  const [signalViewMode, setSignalViewMode] = useState<SignalViewMode>("filtered");
  const [timeWindowSec, setTimeWindowSec] = useState<TimeWindowSec>(5);
  const [stableRpeaks, setStableRpeaks] = useState<number | null>(null);
  const [lastValidCards, setLastValidCards] = useState<LastValidCards>({
    hr: null,
    rmssd: null,
    fs: null,
    rpeaks: null,
  });
  const [displayBattery, setDisplayBattery] = useState<BatterySnapshot>({
    pct: null,
    voltage: null,
    adcVoltage: null,
  });
  const stableRpeaksLastUpdateRef = useRef(0);
  const batteryLastUpdateRef = useRef(0);

  const [alerts, setAlerts] = useState<AlertItem[]>([
    { id: 1, message: "Monitor listo para conectar con backend", time: "10:15", type: "info" },
  ]);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const timerRef = useRef<number | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const lastAlertKeyRef = useRef<string>("");

  const pushAlert = (message: string, type: AlertItem["type"]) => {
    const key = `${type}:${message}`;
    if (lastAlertKeyRef.current === key) return;
    lastAlertKeyRef.current = key;

    setAlerts((prev) => [
      {
        id: Date.now(),
        message,
        time: new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }),
        type,
      },
      ...prev.slice(0, 9),
    ]);
  };

  const apiFetch = async (path: string, options: RequestInit = {}) => {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(options.headers ?? {}),
      },
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    return res.json();
  };

  const loadSessions = async () => {
    try {
      const res = await apiFetch(`/sessions?patient_id=${encodeURIComponent(PATIENT_ID)}&limit=20`);
      const items = res.items ?? [];
      setSessionHistory(items);
      setRecordings(items.length);
    } catch (e) {
      console.error("loadSessions error:", e);
      pushAlert("No se pudo cargar el historial de grabaciones", "warning");
    }
  };

  const stopTimer = () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const startTimer = () => {
    stopTimer();
    timerRef.current = window.setInterval(() => {
      setRecordingTime((prev) => prev + 1);
    }, 1000);
  };

  const connectDevice = () => {
    if (socketRef.current?.readyState === WebSocket.OPEN || socketRef.current?.readyState === WebSocket.CONNECTING) return;

    setConnectionState("connecting");

    const wsParams = new URLSearchParams();
    if (credentials?.apiKey) {
      wsParams.set("api_key", credentials.apiKey);
    } else {
      wsParams.set("username", credentials?.username ?? "");
      wsParams.set("password", credentials?.password ?? "");
    }

    const socket = new WebSocket(`ws://${window.location.hostname}:8000/ws/ecg?${wsParams.toString()}`);
    socketRef.current = socket;

    socket.onopen = () => {
      setIsConnected(true);
      setConnectionState("connected");
      pushAlert("Conexion WebSocket con backend establecida", "info");
      void loadSessions();
    };

    socket.onmessage = (event) => {
      try {
        const payload = typeof event.data === "string" ? JSON.parse(event.data) : event.data;

        const normalized: Payload = {
          device: payload?.device ?? payload?.metrics?.device ?? null,
          gateway: payload?.gateway ?? payload?.metrics?.gateway ?? null,
          metrics: payload?.metrics ?? {},
          samples: {
            t: payload?.samples?.t ?? [],
            v: payload?.samples?.v ?? [],
            raw_v: payload?.samples?.raw_v ?? [],
          },
        };

        setData(normalized);
        if (normalized.metrics?.record_id) {
          setCurrentRecordId(normalized.metrics.record_id);
        }
      } catch (e) {
        console.error("WS parse error:", e);
        pushAlert("Error al interpretar datos del backend", "error");
      }
    };

    socket.onclose = () => {
      setIsConnected(false);
      setConnectionState("disconnected");
      socketRef.current = null;
      stopTimer();
      pushAlert("Conexion WebSocket cerrada", "warning");
    };

    socket.onerror = () => {
      setIsConnected(false);
      setConnectionState("disconnected");
      pushAlert("No se pudo conectar con el backend", "error");
    };
  };

  const disconnectDevice = () => {
    setConnectionState("disconnected");
    setIsConnected(false);
    setIsRecording(false);
    setIsPaused(false);
    setActiveSessionId(null);
    stopTimer();
    setRecordingTime(0);

    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
  };

  useEffect(() => {
    void loadSessions();

    return () => {
      if (socketRef.current) socketRef.current.close();
      stopTimer();
    };
  }, []);


  useEffect(() => {
    let cancelled = false;

    const loadSystemStatus = async () => {
      try {
        const res = await apiFetch("/system/status");
        if (!cancelled) {
          setSystemStatus(res);
        }
      } catch (e) {
        console.error("loadSystemStatus error:", e);
      }
    };

    void loadSystemStatus();
    const id = window.setInterval(() => {
      void loadSystemStatus();
    }, 10000);

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const m = data.metrics ?? {};

  const leadOff = useMemo(() => {
    if (m.lead_off === true) return true;
    if (m.quality === "leads_off") return true;
    if (m.lead_off === false) return false;
    return null;
  }, [m.lead_off, m.quality]);

  const leadOffConfirmed = m.lead_off === true || m.quality === "leads_off";

  const leadStatusLabel = useMemo(() => {
    if (leadOff === true) return "ELECTRODOS DESCONECTADOS";
    if (leadOff === false) return "ELECTRODOS OK";
    return "ELECTRODOS: --";
  }, [leadOff]);

  const leadStatusClass = useMemo(() => {
    if (leadOff === true) return "text-red-400";
    if (leadOff === false) return "text-emerald-400";
    return "text-slate-400";
  }, [leadOff]);

  const visualRpeaks = leadOffConfirmed ? 0 : (m.rpeak_times?.length ?? 0);
  const visualHr = useMemo(() => {
    const peaks = m.rpeak_times ?? [];
    if (leadOffConfirmed || peaks.length < 2) return null;

    const rr = peaks
      .slice(1)
      .map((peakTime, index) => peakTime - peaks[index])
      .filter((value) => value >= 0.3 && value <= 2.5);

    if (!rr.length) return null;
    const bpm = rr.map((value) => 60 / value).sort((a, b) => a - b);
    return bpm[Math.floor(bpm.length / 2)];
  }, [leadOffConfirmed, m.rpeak_times]);

  const rawHr = leadOffConfirmed ? null : (m.hr_median ?? visualHr ?? null);
  const hr = rawHr != null && rawHr >= 60 && rawHr <= 100 ? rawHr : null;
  const rmssd = leadOffConfirmed ? null : (m.rmssd_ms ?? null);
  const fs = m.fs_est ?? null;
  const analysisDuration = leadOffConfirmed ? null : (m.analysis_duration_sec ?? null);
  const rpeaks = leadOffConfirmed ? null : ((m.rpeaks && m.rpeaks > 0) ? m.rpeaks : visualRpeaks || null);
  const displayedRpeaks = stableRpeaks ?? rpeaks;
  const cardHr = hr ?? lastValidCards.hr;
  const cardRmssd = rmssd ?? lastValidCards.rmssd;
  const cardDuration = analysisDuration ?? (isRecording ? timeWindowSec : null);
  const cardRpeaks = displayedRpeaks ?? lastValidCards.rpeaks;
  const diagnosis = leadOffConfirmed ? "Electrodos desconectados" : (m.diagnosis ?? "--");
  const confidence = leadOffConfirmed ? null : (m.confidence ?? null);

  const snrDb = m.snr_db ?? 29;
  const artifactsPct = m.artifacts_pct ?? 3;
  const electrodeLoose = leadOffConfirmed;
  const incomingBatteryLevel = data.metrics?.battery_pct ?? null;
  const batteryLevel = displayBattery.pct;
  const batteryClass =
    batteryLevel == null
      ? "text-slate-500"
      : batteryLevel >= 60
      ? "text-emerald-300"
      : batteryLevel >= 30
      ? "text-amber-300"
      : "text-red-300";

  const deviceName = data.device ?? m.device ?? "--";
  const gatewayName = data.gateway ?? m.gateway ?? window.location.hostname;
  const hwOk = m.hw_ok ?? false;
  const hwError = m.hw_error ?? "";
  const adcChannel = m.adc_channel;
  const adcDataRate = m.adc_data_rate;
  const clientCount = m.clients ?? 0;

  const cpuTone = getSystemTone(systemStatus?.cpu_percent, 60, 80);
  const ramTone = getSystemTone(systemStatus?.ram_percent, 75, 85);
  const diskTone = getSystemTone(systemStatus?.disk_percent, 80, 90);
  const tempTone = getSystemTone(systemStatus?.temperature_c ?? undefined, 65, 75);

  const cpuToneClasses = getToneClasses(cpuTone);
  const ramToneClasses = getToneClasses(ramTone);
  const diskToneClasses = getToneClasses(diskTone);
  const tempToneClasses = getToneClasses(tempTone);

  useEffect(() => {
    if (incomingBatteryLevel == null) return;

    const now = Date.now();
    if (displayBattery.pct == null || now - batteryLastUpdateRef.current >= BATTERY_DISPLAY_UPDATE_MS) {
      setDisplayBattery({
        pct: incomingBatteryLevel,
        voltage: m.battery_voltage_v ?? null,
        adcVoltage: m.battery_adc_voltage_v ?? null,
      });
      batteryLastUpdateRef.current = now;
    }
  }, [incomingBatteryLevel, m.battery_voltage_v, m.battery_adc_voltage_v, displayBattery.pct]);

  useEffect(() => {
    if (!isRecording || leadOffConfirmed || rpeaks == null) {
      setStableRpeaks(null);
      stableRpeaksLastUpdateRef.current = 0;
      return;
    }

    const now = Date.now();
    if (stableRpeaks == null || now - stableRpeaksLastUpdateRef.current >= 20_000) {
      setStableRpeaks(rpeaks);
      stableRpeaksLastUpdateRef.current = now;
    }
  }, [isRecording, leadOffConfirmed, rpeaks, stableRpeaks]);

  useEffect(() => {
    if (!isRecording) return;
    if (recordingTime < 3) return;
    if (leadOffConfirmed) return;

    setLastValidCards((prev) => ({
      hr: hr != null && Number.isFinite(hr) ? hr : prev.hr,
      rmssd: rmssd != null && Number.isFinite(rmssd) && rmssd >= 0 ? rmssd : prev.rmssd,
      fs: fs != null && Number.isFinite(fs) && fs > 0 ? fs : prev.fs,
      rpeaks:
        cardRpeaks != null && Number.isFinite(cardRpeaks) && cardRpeaks > 0
          ? cardRpeaks
          : prev.rpeaks,
    }));
  }, [isRecording, recordingTime, leadOffConfirmed, hr, rmssd, fs, cardRpeaks]);

  const plotDelayActive = isRecording && recordingTime < 3;
  const shouldRenderSignal = isRecording && !plotDelayActive;
  const shouldBlockInvalidSignal = isRecording && leadOffConfirmed;

  const activeSignal = useMemo(() => {
    const filtered = data.samples?.v ?? [];
    const raw = data.samples?.raw_v ?? [];
    return signalViewMode === "raw" ? (raw.length ? raw : filtered) : (filtered.length ? filtered : raw);
  }, [data.samples, signalViewMode]);

  const activeTimeWindowSignal = useMemo(() => {
    const signal = activeSignal ?? [];
    const t = data.samples?.t ?? [];

    if (!signal.length || !t.length || t.length !== signal.length) {
      return signal;
    }

    const lastT = t[t.length - 1];
    const threshold = lastT - timeWindowSec;
    const startIndex = t.findIndex((value) => value >= threshold);

    if (startIndex === -1) return signal;
    return signal.slice(startIndex);
  }, [activeSignal, data.samples?.t, timeWindowSec]);

  const activeTimeWindowT = useMemo(() => {
    const t = data.samples?.t ?? [];
    if (!t.length) return [];

    const lastT = t[t.length - 1];
    const threshold = lastT - timeWindowSec;
    const startIndex = t.findIndex((value) => value >= threshold);

    if (startIndex === -1) return t;
    return t.slice(startIndex);
  }, [data.samples?.t, timeWindowSec]);

  const changeTimeWindow = (next: TimeWindowSec) => {
    setTimeWindowSec(next);
    pushAlert(`Ventana temporal: ${next}s`, "info");
  };

  const saveCapture = () => {
    const canvas = canvasRef.current;
    if (!canvas) {
      pushAlert("No hay captura disponible", "warning");
      return;
    }

    const link = document.createElement("a");
    const safeRecordId = currentRecordId && currentRecordId !== "--" ? currentRecordId : `ECG-${Date.now()}`;
    link.href = canvas.toDataURL("image/png");
    link.download = `${safeRecordId}_${timeWindowSec}s_ecg.png`;
    link.click();

    pushAlert("Captura PNG guardada", "info");
  };

  const downloadSessionPdf = async (sessionId: string, recordId?: string | null) => {
    try {
      const res = await fetch(`${API_BASE}/sessions/report.pdf/${encodeURIComponent(sessionId)}`, {
        headers: {
          ...authHeaders(),
        },
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      const safeName = recordId && recordId !== "--" ? recordId : sessionId;
      a.href = url;
      a.download = `${safeName}_report.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);

      pushAlert(`PDF descargado: ${safeName}`, "info");
    } catch (e) {
      console.error("downloadSessionPdf error:", e);
      pushAlert("No se pudo descargar el PDF de la sesion", "error");
    }
  };

  const downloadSessionZip = async (sessionId: string, recordId?: string | null) => {
    const safeName = recordId && recordId !== "--" ? recordId : sessionId;
    pushAlert(`Preparando ZIP: ${safeName}`, "info");

    try {
      const res = await fetch(`${API_BASE}/sessions/export.zip/${encodeURIComponent(sessionId)}`, {
        headers: {
          ...authHeaders(),
        },
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${safeName}.zip`;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();

      setTimeout(() => {
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      }, 2000);

      pushAlert(`Paquete exportado: ${safeName}`, "info");
    } catch (e) {
      console.error("downloadSessionZip error:", e);
      pushAlert("No se pudo descargar el paquete ZIP", "error");
    }
  };

  const validatePatientFields = () => {
    if (!patientAge || Number.isNaN(Number(patientAge)) || Number(patientAge) <= 0) {
      pushAlert("Edad obligatoria y valida", "warning");
      return false;
    }

    if (!patientSex) {
      pushAlert("Sexo obligatorio", "warning");
      return false;
    }

    return true;
  };

  const startRecording = async () => {
    if (!canRecordEcg) {
      pushAlert("Usuario de solo lectura: no puede grabar ECG", "warning");
      return;
    }

    pushAlert("Intentando iniciar grabacion...", "info");

    if (!validatePatientFields()) return;

    try {
      await apiFetch("/health");
    } catch (healthError) {
      console.error("Backend health check failed:", healthError);
      pushAlert("Backend no disponible; revisa la conexion", "error");
      return;
    }

    if (hwOk === false) {
      pushAlert("Grabacion iniciada sin hardware ECG conectado", "warning");
    }

    try {
      await apiFetch("/patients", {
        method: "POST",
        body: JSON.stringify({
          patient_id: PATIENT_ID,
          display_name: patientName,
          sex: patientSex,
          age: Number(patientAge),
        }),
      });

      const session = await apiFetch("/sessions/start", {
        method: "POST",
        body: JSON.stringify({
          patient_id: PATIENT_ID,
          patient_name: patientName,
          age: Number(patientAge),
          sex: patientSex,
          note: "Grabacion ECG desde monitor",
        }),
      });

      setActiveSessionId(session.session_id ?? null);
      setCurrentRecordId(session.record_id ?? "--");
      setIsRecording(true);
      setIsPaused(false);
      setRecordingTime(0);
      setStableRpeaks(null);
      stableRpeaksLastUpdateRef.current = 0;
      setLastValidCards({ hr: null, rmssd: null, fs: null, rpeaks: null });
      startTimer();

      pushAlert("Grabacion iniciada", "info");
    } catch (e) {
      console.error("startRecording error:", e);
      pushAlert("No se pudo iniciar la grabacion", "error");
    }
  };

  const stopRecording = async () => {
    setIsRecording(false);
    setIsPaused(false);
    stopTimer();

    try {
      if (activeSessionId) {
        await apiFetch(`/sessions/stop/${activeSessionId}`, {
          method: "POST",
          body: JSON.stringify({
            duration_sec: recordingTime,
            note: "Grabacion finalizada desde monitor",
          }),
        });
      }

      setActiveSessionId(null);
      pushAlert(`Grabacion guardada: ${formatTime(recordingTime)}`, "info");
      await loadSessions();
    } catch (e) {
      console.error("stopRecording error:", e);
      pushAlert("No se pudo guardar la grabacion", "error");
    }
  };

  const togglePause = () => {
    if (!isRecording) return;

    if (isPaused) {
      setIsPaused(false);
      startTimer();
      pushAlert("Grabacion reanudada", "info");
      return;
    }

    setIsPaused(true);
    stopTimer();
    pushAlert("Grabacion en pausa", "info");
  };

  const toggleSignalViewMode = () => {
    setSignalViewMode((prev) => {
      const next = prev === "filtered" ? "raw" : "filtered";
      pushAlert(next === "filtered" ? "Mostrando señal filtrada" : "Mostrando señal cruda", "info");
      return next;
    });
  };

  const exportData = async () => {
    try {
      const res = await fetch(`${API_BASE}/sessions/export.xlsx?patient_id=${encodeURIComponent(PATIENT_ID)}&limit=200`, {
        headers: {
          ...authHeaders(),
        },
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "sessions_export.xlsx";
      a.click();
      window.URL.revokeObjectURL(url);

      pushAlert("Excel exportado correctamente", "info");
    } catch (e) {
      console.error("exportData error:", e);
      pushAlert("No se pudo exportar el Excel", "error");
    }
  };

  const showHistoryFn = async () => {
    await loadSessions();
    setShowAlerts(false);
    pushAlert("Historial de grabaciones actualizado", "info");
  };

  useEffect(() => {
    if (connectionState !== "connected") return;

    if (m.quality === "hw_error") {
      pushAlert(hwError || "Error de hardware ECG/ADC", "error");
      return;
    }

    if (leadOffConfirmed) {
      pushAlert("Electrodos desconectados", "error");
      return;
    }

    if ((m.artifacts_pct ?? 0) >= 10) {
      pushAlert("Muchos artefactos detectados en la señal", "warning");
      return;
    }

    if ((m.snr_db ?? 99) < 18) {
      pushAlert("Calidad de señal baja", "warning");
      return;
    }
  }, [connectionState, m.quality, m.artifacts_pct, m.snr_db, leadOffConfirmed, hwError]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { width, height } = canvas;

    ctx.fillStyle = "#020617";
    ctx.fillRect(0, 0, width, height);

    const minor = 10;
    const major = 50;

    for (let x = 0; x <= width; x += minor) {
      ctx.beginPath();
      ctx.strokeStyle = x % major === 0 ? "rgba(30, 41, 59, 0.85)" : "rgba(30, 41, 59, 0.35)";
      ctx.lineWidth = x % major === 0 ? 0.8 : 0.45;
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }

    for (let y = 0; y <= height; y += minor) {
      ctx.beginPath();
      ctx.strokeStyle = y % major === 0 ? "rgba(30, 41, 59, 0.85)" : "rgba(30, 41, 59, 0.35)";
      ctx.lineWidth = y % major === 0 ? 0.8 : 0.45;
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    if (!shouldRenderSignal) {
      ctx.fillStyle = "rgba(2, 6, 23, 0.78)";
      ctx.fillRect(0, 0, width, height);

      ctx.fillStyle = "#e2e8f0";
      ctx.font = "bold 22px system-ui, -apple-system, Segoe UI, Roboto";
      ctx.fillText(plotDelayActive ? "ESTABILIZANDO SENAL" : "MONITOR EN ESPERA", 24, 42);

      ctx.fillStyle = "#94a3b8";
      ctx.font = "14px system-ui, -apple-system, Segoe UI, Roboto";
      if (plotDelayActive) {
        const remaining = Math.max(1, 3 - recordingTime);
        ctx.fillText(`La grafica iniciara en ${remaining}s`, 24, 68);
        ctx.fillText("Capturando una ventana inicial estable", 24, 92);
        return;
      }
      ctx.fillText("Presione Iniciar para visualizar la señal ECG", 24, 68);
      ctx.fillText("La adquisición se mostrará únicamente durante una sesión activa", 24, 92);
      return;
    }

    if (shouldBlockInvalidSignal) {
      ctx.fillStyle = "rgba(2, 6, 23, 0.82)";
      ctx.fillRect(0, 0, width, height);

      ctx.fillStyle = "#f8fafc";
      ctx.font = "bold 22px system-ui, -apple-system, Segoe UI, Roboto";
      ctx.fillText("ESPERANDO CONTACTO DE ELECTRODOS", 24, 42);

      ctx.fillStyle = "#94a3b8";
      ctx.font = "14px system-ui, -apple-system, Segoe UI, Roboto";
      ctx.fillText("Señal no válida para visualización", 24, 68);
      ctx.fillText("Verifique el contacto de RA, LA y RL antes de continuar", 24, 92);
      return;
    }

    const signal = activeTimeWindowSignal ?? [];
    if (signal.length < 6) return;
    const timeValues = activeTimeWindowT ?? [];
    const rpeakTimes = signalViewMode === "filtered" ? (m.rpeak_times ?? []) : [];

    const rows = 1;
    const headerSpace = 60;
    const footerSpace = 26;
    const rowGap = 10;
    const usableHeight = height - headerSpace - footerSpace - rowGap * (rows - 1);
    const rowHeight = usableHeight / rows;
    const pointsPerRow = Math.ceil(signal.length / rows);

    const drawColor = leadOffConfirmed ? "#f59e0b" : signalViewMode === "filtered" ? "#10b981" : "#38bdf8";

    ctx.fillStyle = "#e2e8f0";
    ctx.font = "bold 15px system-ui, -apple-system, Segoe UI, Roboto";
    ctx.fillText(`Paciente: ${patientName || "Paciente Demo"}`, 18, 24);
    ctx.fillText(`BPM: ${isRecording && cardHr != null ? Math.round(cardHr) : "--"}`, 18, 46);

    ctx.fillStyle = "#94a3b8";
    ctx.font = "12px system-ui, -apple-system, Segoe UI, Roboto";
    ctx.fillText(`Calidad: ${isRecording ? (m.quality ?? "--") : "--"}`, 190, 24);
    ctx.fillText(`Fecha: ${isRecording ? formatDateTime(m.study_date ?? new Date().toISOString()) : "--"}`, 190, 46);
    ctx.fillText(`Record ID: ${currentRecordId}`, width - 250, 24);
    ctx.fillText(`Edad: ${patientAge || "--"} | Sexo: ${patientSex || "--"} | Ventana: ${timeWindowSec}s`, width - 250, 46);

    ctx.strokeStyle = drawColor;
    ctx.lineWidth = signalViewMode === "filtered" ? 2 : 1.5;

    for (let row = 0; row < rows; row++) {
      const start = row * pointsPerRow;
      const end = Math.min(signal.length, start + pointsPerRow);
      const segment = signal.slice(start, end);
      if (segment.length < 2) continue;

      const rowTop = headerSpace + row * (rowHeight + rowGap);
      const rowCenter = rowTop + rowHeight / 2;

      const median = getPercentile(segment, 0.5);
      const p05 = getPercentile(segment, 0.05);
      const p95 = getPercentile(segment, 0.95);
      const robustSpan = Math.max(p95 - p05, 0.03);
      const rowGain = Math.min(3200, Math.max(120, ((rowHeight * 0.72) / robustSpan) * zoomLevel));
      const step = width / Math.max(1, segment.length - 1);

      ctx.beginPath();
      for (let i = 0; i < segment.length; i++) {
        const x = i * step;
        const yRaw = rowCenter - (segment[i] - median) * rowGain;
        const y = Math.max(rowTop + 6, Math.min(rowTop + rowHeight - 6, yRaw));

        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      if (rpeakTimes.length && timeValues.length === signal.length) {
        const tStart = timeValues[0];
        const tEnd = timeValues[timeValues.length - 1];
        const tSpan = Math.max(0.001, tEnd - tStart);

        ctx.fillStyle = "#ef4444";
        ctx.strokeStyle = "#fecaca";
        ctx.lineWidth = 1.4;
        rpeakTimes.forEach((peakTime) => {
          if (peakTime < tStart || peakTime > tEnd) return;
          const peakIndex = Math.min(
            segment.length - 1,
            Math.max(0, Math.round(((peakTime - tStart) / tSpan) * (segment.length - 1)))
          );
          const xPeak = peakIndex * step;
          const yRawPeak = rowCenter - (segment[peakIndex] - median) * rowGain;
          const yPeak = Math.max(rowTop + 6, Math.min(rowTop + rowHeight - 6, yRawPeak));

          ctx.beginPath();
          ctx.arc(xPeak, yPeak, 5, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        });

        ctx.fillStyle = "#fecaca";
        ctx.font = "bold 11px system-ui, -apple-system, Segoe UI, Roboto";
        ctx.fillText(`R detectados: ${cardRpeaks ?? "--"}`, 10, rowTop + 30);
      }

      ctx.strokeStyle = "rgba(148, 163, 184, 0.16)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, rowCenter);
      ctx.lineTo(width, rowCenter);
      ctx.stroke();

      ctx.fillStyle = "#94a3b8";
      ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas";
      ctx.fillText(LEAD_LABEL, 10, rowTop + 14);

      ctx.strokeStyle = drawColor;
      ctx.lineWidth = signalViewMode === "filtered" ? 2 : 1.5;
    }

    ctx.fillStyle = "#94a3b8";
    ctx.font = "bold 12px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas";
    ctx.fillText(SPEED_LABEL, width - 165, height - 8);
    ctx.fillText(GAIN_LABEL, width - 78, height - 8);

    if (leadOffConfirmed) {
      ctx.fillStyle = "rgba(2, 6, 23, 0.68)";
      ctx.fillRect(0, 0, width, height);

      ctx.fillStyle = "#f59e0b";
      ctx.font = "bold 20px system-ui, -apple-system, Segoe UI, Roboto";
      ctx.fillText("ELECTRODOS DESCONECTADOS", 24, 36);

      ctx.fillStyle = "#cbd5e1";
      ctx.font = "13px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas";
      ctx.fillText("Conecta RA / LA / RL para continuar medicion", 24, 58);
    }

    if (isPaused) {
      ctx.fillStyle = "rgba(2, 6, 23, 0.28)";
      ctx.fillRect(0, 0, width, height);

      ctx.fillStyle = "#f8fafc";
      ctx.font = "bold 16px system-ui, -apple-system, Segoe UI, Roboto";
      ctx.fillText("SEÑAL EN PAUSA", 24, 84);
    }
  }, [activeTimeWindowSignal, activeTimeWindowT, cardRpeaks, leadOffConfirmed, zoomLevel, isPaused, signalViewMode, patientName, patientAge, patientSex, currentRecordId, cardHr, m.demo_loop, m.quality, m.rpeak_times, m.study_date, timeWindowSec, recordingTime, plotDelayActive, shouldRenderSignal, shouldBlockInvalidSignal]);

  return (
    <div className="min-h-screen bg-slate-950 text-white font-sans">
      <div className="mx-auto max-w-7xl px-4 py-6">
        <div className="flex justify-between items-start mb-6">
          <button
            onClick={() => {
              logout();
              onBack?.();
            }}
            className="bg-slate-800 hover:bg-slate-700 p-2 rounded-xl text-white flex items-center gap-2 transition-all"
          >
            <ArrowLeft size={18} /> Volver
          </button>

          <div className="flex flex-col items-end">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Activity className={isConnected ? "text-emerald-400 animate-pulse" : "text-slate-600"} />
              MONITOR MEDINIC
            </h2>

            <span className={`text-[10px] font-bold ${isConnected ? "text-emerald-500" : "text-red-500"}`}>
              {isConnected ? "● TRANSMISION ACTIVA" : "○ SIN CONEXION CON BACKEND"}
            </span>

            <div className="mt-2 flex items-center gap-3 text-[10px] font-mono">
              <span className={`flex items-center gap-1 ${leadStatusClass}`}>
                <Plug size={14} /> {leadStatusLabel}
              </span>

              <span className="text-slate-400 flex items-center gap-1">
                <Power size={14} />
                SDN: <span className="text-white">{m.sdn == null ? "--" : m.sdn ? "ON" : "OFF"}</span>
              </span>

              <button
                onClick={() => setShowAlerts((s) => !s)}
                className="ml-2 inline-flex items-center gap-1 text-slate-300 hover:text-white"
                title="Alertas"
              >
                <Bell size={14} />
                <span className="text-[10px]">{alerts.length}</span>
              </button>
            </div>

            <div className="mt-1 text-[10px] font-mono text-slate-400">
              LO+: <span className="text-white">{fmtBool(m.lo_plus)}</span> LO-:{" "}
              <span className="text-white">{fmtBool(m.lo_minus)}</span> Q:{" "}
              <span className="text-white">{isRecording ? (m.quality ?? "--") : "--"}</span>
            </div>

            <div className="mt-1 text-[10px] font-mono text-slate-400">
              Bateria:{" "}
              <span
                title={
                  displayBattery.voltage != null
                    ? `Banco: ${displayBattery.voltage.toFixed(2)} V | A1: ${displayBattery.adcVoltage?.toFixed(3) ?? "--"} V`
                    : "Voltaje de bateria no disponible"
                }
                className={batteryClass}
              >
                {batteryLevel != null ? `${Math.round(batteryLevel)}%` : "--"}
              </span>
            </div>
          </div>
        </div>

        {showAlerts && (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/30 px-5 py-4 mb-6">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-semibold text-slate-200">Alertas recientes</div>
              <button onClick={() => setShowAlerts(false)} className="text-xs text-slate-400 hover:text-white">
                Cerrar
              </button>
            </div>

            <div className="space-y-2 max-h-48 overflow-y-auto text-sm">
              {alerts.map((a) => (
                <div
                  key={a.id}
                  className="flex items-start justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="text-slate-200">{a.message}</div>
                    <div className="text-[11px] text-slate-500">{a.time}</div>
                  </div>
                  <span
                    className={`text-[11px] px-2 py-0.5 rounded-full border ${
                      a.type === "error"
                        ? "border-red-500/30 text-red-300 bg-red-500/10"
                        : a.type === "warning"
                        ? "border-amber-500/30 text-amber-300 bg-amber-500/10"
                        : "border-sky-500/30 text-sky-300 bg-sky-500/10"
                    }`}
                  >
                    {a.type}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="rounded-2xl border border-slate-800 bg-slate-900/30 px-5 py-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-full bg-[#445A99]/60 grid place-items-center">
              <User size={18} className="text-white/90" />
            </div>
            <div>
              <div className="font-semibold">{patientName || "Paciente Demo"}</div>
              <div className="text-xs text-white/60">ID: {PATIENT_ID}</div>
            </div>
          </div>

          <span className="self-start md:self-auto rounded-full bg-green-500/15 text-green-300 border border-green-500/25 px-3 py-1 text-xs font-semibold">
            {isConnected ? "online" : "offline"}
          </span>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-4 mb-6">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/30 px-4 py-4">
            <label className="block text-xs text-slate-400 mb-2">Paciente</label>
            <input
              value={patientName}
              onChange={(e) => setPatientName(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
            />
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/30 px-4 py-4">
            <label className="block text-xs text-slate-400 mb-2">Edad *</label>
            <input
              value={patientAge}
              onChange={(e) => setPatientAge(e.target.value)}
              type="number"
              min="1"
              max="120"
              className="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
            />
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/30 px-4 py-4">
            <label className="block text-xs text-slate-400 mb-2">Sexo *</label>
            <select
              value={patientSex}
              onChange={(e) => setPatientSex(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
            >
              <option value="">Seleccionar</option>
              <option value="F">Femenino</option>
              <option value="M">Masculino</option>
              <option value="O">Otro</option>
            </select>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/30 px-4 py-4">
            <div className="text-xs text-slate-400 mb-2">Record ID</div>
            <div className="rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-emerald-300 font-mono">
              {currentRecordId}
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/30 overflow-hidden shadow-2xl mb-6">
          <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Signal size={16} className="text-emerald-300" />
              <span className="font-semibold">Señal ECG - Tiempo Real</span>
            </div>

            <div className="flex items-center gap-2 text-white/70 text-sm">
              <button
                onClick={toggleSignalViewMode}
                className={`px-3 py-1 rounded-lg border text-xs ${
                  signalViewMode === "filtered"
                    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                    : "border-sky-500/40 bg-sky-500/10 text-sky-300"
                }`}
                title="Alternar señal cruda/filtrada"
              >
                {signalViewMode === "filtered" ? "Filtrada" : "Cruda"}
              </button>

              {[2, 5, 10].map((value) => (
                <button
                  key={value}
                  onClick={() => changeTimeWindow(value as TimeWindowSec)}
                  className={`px-3 py-1 rounded-lg border text-xs ${
                    timeWindowSec === value
                      ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                      : "border-slate-700 bg-slate-900/20 text-slate-300 hover:bg-slate-800"
                  }`}
                  title={`Ver ${value} segundos`}
                >
                  {value}s
                </button>
              ))}

              <button
                onClick={saveCapture}
                className="px-3 py-1 rounded-lg border border-slate-700 bg-slate-900/20 text-slate-300 hover:bg-slate-800 inline-flex items-center gap-1 text-xs"
                title="Guardar captura PNG"
              >
                <Camera size={14} />
                <span>Captura</span>
              </button>

              <button
                onClick={() => setZoomLevel((z) => Math.max(0.5, z - 0.25))}
                className="px-2 py-1 rounded-lg hover:bg-slate-800"
                title="Alejar"
              >
                −
              </button>
              <button
                onClick={() => setZoomLevel((z) => Math.min(2, z + 0.25))}
                className="px-2 py-1 rounded-lg hover:bg-slate-800"
                title="Acercar"
              >
                +
              </button>
            </div>
          </div>

          <div className="px-5 py-3 border-b border-slate-800 flex flex-col gap-2 text-xs text-slate-300 md:flex-row md:items-center md:justify-between">
            <div className="flex flex-wrap items-center gap-4">
              <span>BPM: <span className="text-white font-semibold">{isRecording && cardHr != null ? Math.round(cardHr) : "--"}</span></span>
              <span>Calidad: <span className="text-white font-semibold">{m.quality ?? "--"}</span></span>
              <span>Lead: <span className="text-white font-semibold">{m.lead ?? LEAD_LABEL}</span></span>
              <span>Fecha: <span className="text-white font-semibold">{isRecording ? formatDateTime(m.study_date ?? new Date().toISOString()) : "--"}</span></span>
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <span>Ventana: <span className="text-white font-semibold">{timeWindowSec}s</span></span>
              <span>Velocidad: <span className="text-white font-semibold">{m.speed ?? SPEED_LABEL}</span></span>
              <span>Ganancia: <span className="text-white font-semibold">{m.gain ?? GAIN_LABEL}</span></span>
            </div>
          </div>

          <div className="p-4">
            <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden aspect-video md:aspect-auto md:h-[520px]">
              <canvas ref={canvasRef} width={1100} height={520} className="w-full h-full" />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-slate-800 p-4 rounded-2xl border border-slate-700 text-center shadow-lg">
            <Heart className={`mx-auto mb-2 ${isConnected ? "text-red-500 animate-pulse" : "text-slate-600"}`} />
            <p className="text-3xl font-black leading-none">{isRecording && cardHr != null ? Math.round(cardHr) : "--"}</p>
            <p className="text-[10px] text-slate-500 font-bold uppercase mt-1">BPM</p>
          </div>

          <div className="bg-slate-800 p-4 rounded-2xl border border-slate-700 text-center shadow-lg">
            <Zap className="mx-auto mb-2 text-blue-400" />
            <p className="text-3xl font-black leading-none">{isRecording && cardRmssd != null ? Math.round(cardRmssd) : "--"}</p>
            <p className="text-[10px] text-slate-500 font-bold uppercase mt-1">RMSSD (ms)</p>
          </div>

          <div className="bg-slate-800 p-4 rounded-2xl border border-slate-700 text-center shadow-lg">
            <Signal className="mx-auto mb-2 text-emerald-400" />
            <p className="text-3xl font-black leading-none">{isRecording && cardDuration != null ? `${Math.round(cardDuration)}s` : "--"}</p>
            <p className="text-[10px] text-slate-500 font-bold uppercase mt-1">Duracion analisis</p>
          </div>

          <div className="bg-slate-800 p-4 rounded-2xl border border-slate-700 text-center shadow-lg">
            <Activity className="mx-auto mb-2 text-amber-400" />
            <p className="text-3xl font-black leading-none">{isRecording && cardRpeaks != null ? cardRpeaks : "--"}</p>
            <p className="text-[10px] text-slate-500 font-bold uppercase mt-1">Picos R</p>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/30 px-5 py-4 mt-6">
          <div className="flex items-center gap-2 text-slate-300 text-sm mb-3">
            <Signal size={16} />
            <span className="font-semibold">Calidad de Señal</span>
          </div>

          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-slate-300">SNR (Signal-to-Noise)</span>
              <div className="flex items-center gap-2">
                <span className="text-white">{isRecording && snrDb != null ? `${Math.round(snrDb)} dB` : "--"}</span>
                <span
                  className={`px-2 py-0.5 rounded-full text-xs border ${
                    isRecording && snrDb != null
                      ? (snrDb > 22
                      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/25"
                      : snrDb > 18
                      ? "bg-amber-500/15 text-amber-300 border-amber-500/25"
                      : "bg-red-500/15 text-red-300 border-red-500/25")
                      : "bg-slate-500/15 text-slate-300 border-slate-500/25"
                  }`}
                >
                  {isRecording && snrDb != null ? (snrDb > 22 ? "Excelente" : snrDb > 18 ? "Bueno" : "Bajo") : "--"}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-300">Artefactos detectados</span>
              <div className="flex items-center gap-2">
                <span className="text-white">{isRecording && artifactsPct != null ? `${Math.round(artifactsPct)}%` : "--"}</span>
                <span
                  className={`px-2 py-0.5 rounded-full text-xs border ${
                    isRecording && artifactsPct != null
                      ? (artifactsPct < 5
                      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/25"
                      : artifactsPct < 10
                      ? "bg-amber-500/15 text-amber-300 border-amber-500/25"
                      : "bg-red-500/15 text-red-300 border-red-500/25")
                      : "bg-slate-500/15 text-slate-300 border-slate-500/25"
                  }`}
                >
                  {isRecording && artifactsPct != null ? (artifactsPct < 5 ? "Bajo" : artifactsPct < 10 ? "Medio" : "Alto") : "--"}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-300">Electrodo suelto</span>
              <div className="flex items-center gap-2">
                <span className="text-white">{isRecording ? (electrodeLoose ? "Si" : "No") : "--"}</span>
                <span
                  className={`px-2 py-0.5 rounded-full text-xs border ${
                    isRecording
                      ? (electrodeLoose
                      ? "bg-red-500/15 text-red-300 border-red-500/25"
                      : "bg-emerald-500/15 text-emerald-300 border-emerald-500/25")
                      : "bg-slate-500/15 text-slate-300 border-slate-500/25"
                  }`}
                >
                  {isRecording ? (electrodeLoose ? "Verificar" : "OK") : "--"}
                </span>
              </div>
            </div>
          </div>
        </div>

        <section className="mt-6 space-y-3">
          <div className="hidden">
            <button
              onClick={showHistoryFn}
              className="h-16 rounded-xl border border-slate-800 bg-slate-900/20 hover:bg-slate-900/35 text-slate-300 text-xs flex flex-col items-center justify-center gap-1"
            >
              <span>🕘</span>
              <span>Historial HRV</span>
            </button>

            <button
              onClick={exportData}
              className="h-16 rounded-xl border border-slate-800 bg-slate-900/20 hover:bg-slate-900/35 text-slate-300 text-xs flex flex-col items-center justify-center gap-1"
            >
              <span>⬇️</span>
              <span>Exportar</span>
            </button>

            <button
              onClick={() => setShowAlerts((s) => !s)}
              className="relative h-16 rounded-xl border border-slate-800 bg-slate-900/20 hover:bg-slate-900/35 text-slate-300 text-xs flex flex-col items-center justify-center gap-1"
            >
              <span>🔔</span>
              <span>Alertas</span>
              {alerts.length > 0 && (
                <span className="absolute top-2 right-2 w-5 h-5 rounded-full bg-red-500 text-white text-[10px] grid place-items-center">
                  {alerts.length}
                </span>
              )}
            </button>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/30 px-5 py-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-slate-200">Conexión del dispositivo</div>
              <div className="text-[11px] text-slate-400 font-mono">
                Estado:{" "}
                <span
                  className={
                    connectionState === "connected"
                      ? "text-emerald-400"
                      : connectionState === "connecting"
                      ? "text-amber-400"
                      : "text-slate-500"
                  }
                >
                  {connectionState === "connected"
                    ? "🟢 Conectado"
                    : connectionState === "connecting"
                    ? "🟡 Conectando..."
                    : "🔴 Desconectado"}
                </span>
              </div>
            </div>

            <div className="mt-3">
              {connectionState === "disconnected" ? (
                <button
                  onClick={connectDevice}
                  className="w-full h-12 rounded-xl border border-red-500/40 bg-red-500/15 text-red-300 hover:bg-red-500/25 flex items-center justify-center gap-2"
                >
                  <span className="text-lg">🔴</span>
                  <span>Conectar Dispositivo</span>
                </button>
              ) : connectionState === "connecting" ? (
                <button
                  disabled
                  className="w-full h-12 rounded-xl border border-amber-500/40 bg-amber-500/15 text-amber-300 flex items-center justify-center gap-2"
                >
                  <span>🟡</span>
                  <span>Conectando...</span>
                </button>
              ) : (
                <div className="space-y-3">
                  <div className="w-full h-12 rounded-xl border border-emerald-500/40 bg-emerald-500/15 text-emerald-300 flex items-center justify-center gap-2">
                    <span>🟢</span>
                    <span>Backend Conectado</span>
                    {isRecording && (
                      <span className="ml-2 text-xs text-red-300">
                        {isPaused ? "⏸" : "●"} {formatTime(recordingTime)}
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    {!canRecordEcg ? (
                      <div className="col-span-2 h-12 rounded-xl border border-slate-700 bg-slate-900/35 text-slate-300 flex items-center justify-center">
                        Solo lectura
                      </div>
                    ) : !isRecording ? (
                      <button type="button" onClick={startRecording} className="col-span-2 h-12 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white">
                        ▶ Iniciar
                      </button>
                    ) : (
                      <>
                        <button onClick={togglePause} className="h-12 rounded-xl bg-amber-600 hover:bg-amber-700 text-white">
                          {isPaused ? "▶" : "⏸"}
                        </button>
                        <button onClick={stopRecording} className="h-12 rounded-xl bg-red-600 hover:bg-red-700 text-white">
                          ■ Detener
                        </button>
                      </>
                    )}

                    <button
                      onClick={disconnectDevice}
                      className="h-12 rounded-xl border border-slate-700 bg-slate-900/20 hover:bg-slate-900/35 text-slate-200"
                      title="Desconectar"
                    >
                      ⛔
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/30 px-5 py-4 mt-6">
          <div className="text-sm text-slate-300 font-semibold mb-3">Información del Dispositivo</div>

          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-400">Dispositivo:</span>
              <span className="text-white">{deviceName}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Gateway:</span>
              <span className="text-white">{gatewayName}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Hardware ADC:</span>
              <span className={hwOk ? "text-emerald-300" : "text-red-300"}>{hwOk ? "Disponible" : "No disponible"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Canal ADC:</span>
              <span className="text-white">{adcChannel != null ? `A${adcChannel}` : "--"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">ADC data rate:</span>
              <span className="text-white">{adcDataRate != null ? `${adcDataRate} SPS` : "--"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Frecuencia muestreo:</span>
              <span className="text-white">{fs != null ? `${Math.round(fs)} Hz` : "--"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Ventana temporal:</span>
              <span className="text-white">{timeWindowSec}s</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Vista de señal:</span>
              <span className={signalViewMode === "filtered" ? "text-emerald-300" : "text-sky-300"}>
                {signalViewMode === "filtered" ? "Filtrada" : "Cruda"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Lead:</span>
              <span className="text-white">{m.lead ?? LEAD_LABEL}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Clientes WS:</span>
              <span className="text-white">{clientCount}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Grabaciones:</span>
              <span className="text-white">{recordings}</span>
            </div>
            {!!hwError && (
              <div className="flex justify-between gap-4">
                <span className="text-slate-400">Error hardware:</span>
                <span className="text-right text-red-300">{hwError}</span>
              </div>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/30 px-5 py-4 mt-6">
          <div className="text-sm text-slate-300 font-semibold mb-3">Estado del Sistema</div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className={`rounded-xl border px-3 py-2 ${cpuToneClasses.box}`}>
              <div className="text-slate-500 text-xs">CPU</div>
              <div className={`font-semibold ${cpuToneClasses.value}`}>
                {systemStatus?.cpu_percent != null ? `${systemStatus.cpu_percent}%` : "--"}
              </div>
            </div>

            <div className={`rounded-xl border px-3 py-2 ${ramToneClasses.box}`}>
              <div className="text-slate-500 text-xs">RAM</div>
              <div className={`font-semibold ${ramToneClasses.value}`}>
                {systemStatus?.ram_percent != null ? `${systemStatus.ram_percent}%` : "--"}
              </div>
            </div>

            <div className={`rounded-xl border px-3 py-2 ${diskToneClasses.box}`}>
              <div className="text-slate-500 text-xs">Disco</div>
              <div className={`font-semibold ${diskToneClasses.value}`}>
                {systemStatus?.disk_percent != null ? `${systemStatus.disk_percent}%` : "--"}
              </div>
            </div>

            <div className={`rounded-xl border px-3 py-2 ${tempToneClasses.box}`}>
              <div className="text-slate-500 text-xs">Temp</div>
              <div className={`font-semibold ${tempToneClasses.value}`}>
                {systemStatus?.temperature_c != null ? `${systemStatus.temperature_c} C` : "--"}
              </div>
            </div>
          </div>

          <div className="mt-3 flex items-center justify-between text-xs">
            <span className="text-slate-500">Uptime</span>
            <span className="text-slate-200">{formatUptime(systemStatus?.uptime_s)}</span>
          </div>

          <div className="mt-2 flex items-center justify-between text-xs">
            <span className="text-slate-500">Backend</span>
            <span className={systemStatus?.backend_ok ? "text-emerald-300" : "text-red-300"}>
              {systemStatus?.backend_ok ? "OK" : "Error"}
            </span>
          </div>

          <div className="mt-2 flex items-center justify-between text-xs">
            <span className="text-slate-500">ADC</span>
            <span className={systemStatus?.adc_ok ? "text-emerald-300" : "text-amber-300"}>
              {systemStatus?.adc_ok ? "Disponible" : "Revisar"}
            </span>
          </div>
        </div>


        <div className="rounded-2xl border border-slate-800 bg-slate-900/30 px-5 py-4 mt-6">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm text-slate-300 font-semibold">Historial HRV</div>
            <div className="text-xs text-slate-500">{sessionHistory.length} registro(s)</div>
          </div>

          <div className="space-y-3 text-sm">
            {sessionHistory.length === 0 ? (
              <div className="text-slate-500">No hay grabaciones guardadas todavía.</div>
            ) : (
              sessionHistory.map((item) => {
                const sessionMetrics = parseSessionMetrics(item.metrics_json);
                const quality = sessionMetrics.quality ?? "--";
                const bpm = sessionMetrics.hr_median != null ? Math.round(sessionMetrics.hr_median) : "--";
                const rmssdValue = sessionMetrics.rmssd_ms != null ? Math.round(sessionMetrics.rmssd_ms) : "--";
                const startedAt = item.started_at_iso ?? item.started_at;
                const endedAt = item.ended_at_iso ?? item.stopped_at;
                const recordId = sessionMetrics.record_id ?? "--";

                return (
                  <div
                    key={item.session_id}
                    className="rounded-2xl border border-slate-800 bg-slate-950/40 px-4 py-3"
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                      <div className="min-w-0">
                        <div className="text-slate-200 font-medium">{sessionMetrics.patient_name || item.patient_id || PATIENT_ID}</div>
                        <div className="text-[11px] text-slate-500">
                          Inicio: {formatDateTime(startedAt)} | Fin: {formatDateTime(endedAt)}
                        </div>
                        <div className="text-[11px] text-slate-500 break-all">
                          Sesion: {item.session_id}
                        </div>
                        <div className="text-[11px] text-slate-500 break-all">
                          Record ID: {recordId} | Edad: {sessionMetrics.age ?? "--"} | Sexo: {sessionMetrics.sex ?? "--"}
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 lg:justify-end lg:max-w-[56%]">
                        <span className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300">
                          Duracion: {formatTime(Math.round(item.duration_sec ?? 0))}
                        </span>
                        <span
                          className={`rounded-full border px-2 py-1 text-[11px] ${
                            quality === "ok" || quality === "good"
                              ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300"
                              : quality === "leads_off" || quality === "hw_error"
                              ? "border-red-500/25 bg-red-500/10 text-red-300"
                              : "border-amber-500/25 bg-amber-500/10 text-amber-300"
                          }`}
                        >
                          Calidad: {quality}
                        </span>
                        <span className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300">
                          BPM: {bpm}
                        </span>
                        <span className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300">
                          RMSSD: {rmssdValue}
                        </span>
                        <span className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300">
                          Lead: {sessionMetrics.lead ?? LEAD_LABEL}
                        </span>
                        <button
                          onClick={() => downloadSessionPdf(item.session_id, recordId)}
                          className="inline-flex items-center gap-1 rounded-full border border-sky-500/25 bg-sky-500/10 px-3 py-1 text-[11px] text-sky-300 hover:bg-sky-500/20"
                          title="Descargar PDF de esta sesion"
                        >
                          <FileText size={12} />
                          <span>PDF</span>
                        </button>
                        <button
                          onClick={() => downloadSessionZip(item.session_id, recordId)}
                          className="inline-flex items-center gap-1 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1 text-[11px] text-emerald-300 hover:bg-emerald-500/20"
                          title="Descargar paquete completo: DAT, HEA, ATR, JSON y graficas PNG"
                        >
                          <Download size={12} />
                          <span>ZIP</span>
                        </button>
                      </div>
                    </div>

                    <div className="mt-2 text-[11px] text-slate-500">
                      {item.note || sessionMetrics.interpretation || "Sin nota"}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="mt-4 text-center text-[11px] text-slate-400">
          {m.note ? <span className="font-mono">note: {m.note}</span> : null}
        </div>

        <p className="mt-6 text-center text-[10px] text-slate-600 font-mono tracking-widest uppercase">
          Nodo: {window.location.hostname}:8000 | Tesis de Ingeniería Electrónica
        </p>
      </div>
    </div>
  );
}
