# R-peak detector: mean+2·SD → median + k·MAD

`backend_iot.py` and `postprocess_ecg.py` previously detected R peaks with an adaptive
threshold `mean(x) + 2·SD(x)` (metrics path), plus two other thresholds (`1.7·SD` for the
WebSocket monitor markers, `1.8·SD` for exported plots) that could disagree with the
metrics path on the same signal.

All three paths now call the same detector:

- Filter: Butterworth bandpass, order 2, 0.5–min(40, 0.8·Nyquist) Hz, `filtfilt`.
- Feature: squared first difference, 150 ms centred moving-average integration.
- Threshold: `median(integrated) + k·MAD(integrated)` within the window (unscaled MAD).
- Peak candidates: `scipy.signal.find_peaks(height=threshold, distance=250 ms)` on the
  integrated signal.
- Localization: argmax of `|filtered|` within ±150 ms of each integrator peak.
- Refractory: 250 ms, keeping the larger-amplitude peak when two localized peaks collide.
- Unit of processing: non-overlapping 10 s windows (`WINDOW_S`), matching the live
  acquisition buffer. The export path (`build_clinical_png_bytes`,
  `build_qrs_zoom_png_bytes`) used to run the threshold once over the whole recorded
  session; it now tiles the same way via `windowed_mad_pipeline`, so metrics, WebSocket
  markers, and exported plots use the same unit of processing, not just the same formula.

Default `k = 8.0`, overridable with the `ECG_MAD_K` environment variable
(`ECG_MAD_INTEGRATION_S`, `ECG_MAD_REFRACTORY_S`, `ECG_MAD_LOCALIZATION_S` for the other
parameters). `k = 8` was selected on a development subset of the MIT-BIH Arrhythmia
Database (DS1, 22 records) before evaluating the held-out records, and the detector code
and every parameter were verified to reproduce the offline benchmark exactly (same peaks,
sample for sample) on all 48 MIT-BIH records and on a separate 35-participant beat
collection. Publication experiments should keep `k = 8` and not re-tune it on the
evaluation set. This backend integration has not yet been tested on the Raspberry Pi
hardware (effective sampling rate/jitter, CPU/memory/latency, and the double-detection
mode near T waves seen in MIT-BIH record 113 still need to be checked before this replaces
the version currently in production).

`process_window()` now reports `detector="mad"` and `detector_k` alongside the existing
metrics fields.
