import numpy as np
from scipy import signal

def bandpass(x: np.ndarray, fs: float, low: float, high: float, order: int = 3) -> np.ndarray:
    b, a = signal.butter(order, [low, high], btype="bandpass", fs=fs)
    return signal.filtfilt(b, a, x)

def notch(x: np.ndarray, fs: float, f0: float = 60.0, q: float = 30.0) -> np.ndarray:
    b, a = signal.iirnotch(w0=f0, Q=q, fs=fs)
    return signal.filtfilt(b, a, x)

def pan_tompkins_rpeaks(x: np.ndarray, fs: float,
                        f_notch: float = 60.0, q_notch: float = 30.0,
                        bp_low: float = 5.0, bp_high: float = 15.0,
                        refractory_s: float = 0.25) -> np.ndarray:
    """
    Detector tipo Pan–Tompkins (versión práctica):
    - notch (opcional) + bandpass 5–15 Hz (QRS)
    - derivada, cuadrado, integración móvil
    - umbral adaptativo (mediana + MAD) y find_peaks
    Devuelve índices de R-peaks sobre la señal filtrada.
    """
    if len(x) < int(fs * 2):
        return np.array([], dtype=int)

    # Filtrado para detección
    xd = notch(x, fs, f0=f_notch, q=q_notch)
    xd = bandpass(xd, fs, bp_low, bp_high, order=3)

    # Derivada + cuadrado
    dx = np.diff(xd, prepend=xd[0])
    sq = dx * dx

    # Integración móvil ~150 ms
    win = max(1, int(0.150 * fs))
    mwa = np.convolve(sq, np.ones(win) / win, mode="same")

    # Umbral robusto (MAD)
    med = np.median(mwa)
    mad = np.median(np.abs(mwa - med)) + 1e-12
    thr = med + 5.0 * mad  # si detecta pocos, baja a 4.0; si detecta muchos, sube a 6.0

    distance = max(1, int(refractory_s * fs))
    peaks, props = signal.find_peaks(mwa, height=thr, distance=distance)

    if len(peaks) == 0:
        return np.array([], dtype=int)

    # Refinar: para cada peak de mwa, buscar máximo local en |x| (señal original/filtrada main)
    # Aquí usamos la señal original para que coincida con la morfología.
    search = int(0.08 * fs)  # ±80 ms
    abs_x = np.abs(x)
    r = []
    for p in peaks:
        a = max(p - search, 0)
        b = min(p + search + 1, len(abs_x))
        r.append(a + int(np.argmax(abs_x[a:b])))

    r = np.array(sorted(set(r)), dtype=int)
    return r

def estimate_qrs_width(x: np.ndarray, r_peaks: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """
    Estimación práctica de onset/offset del QRS alrededor de cada R:
    - Busca en ventana ±120 ms
    - Usa energía de derivada para localizar donde "empieza/termina" el complejo
    Retorna onset_idx, offset_idx (mismos tamaños que r_peaks cuando posible)
    """
    if len(r_peaks) == 0:
        return np.array([], dtype=int), np.array([], dtype=int)

    onset = []
    offset = []

    # señal "energía" para delimitar QRS
    dx = np.diff(x, prepend=x[0])
    e = np.abs(dx)

    w_left = int(0.12 * fs)   # 120 ms
    w_right = int(0.12 * fs)

    for r in r_peaks:
        a = max(r - w_left, 0)
        b = min(r + w_right, len(x) - 1)

        seg_e = e[a:b]
        if len(seg_e) < 10:
            continue

        # Umbral local: 20% del pico de energía del segmento
        thr = 0.20 * np.max(seg_e)

        # onset: último punto antes de r donde energía cae por debajo del umbral
        left = e[a:r]
        if len(left) == 0:
            on = a
        else:
            idx = np.where(left < thr)[0]
            on = a + (idx[-1] if len(idx) else 0)

        # offset: primer punto después de r donde energía cae por debajo del umbral
        right = e[r:b]
        if len(right) == 0:
            off = b
        else:
            idx2 = np.where(right < thr)[0]
            off = r + (idx2[0] if len(idx2) else (len(right) - 1))

        onset.append(on)
        offset.append(off)

    return np.array(onset, dtype=int), np.array(offset, dtype=int)

def r_amplitude(x: np.ndarray, r_peaks: np.ndarray) -> np.ndarray:
    """
    Amplitud de R (en unidades de la señal: voltios).
    """
    if len(r_peaks) == 0:
        return np.array([], dtype=float)
    r_peaks = np.clip(r_peaks, 0, len(x) - 1)
    return x[r_peaks].astype(float)

