# Protocolo de validación en Raspberry Pi

Responde el "deployment gate" de `backend/MAD_INTEGRATION.md` (los 5 puntos que ese documento exige antes de que este backend con MAD reemplace producción) y las limitaciones marcadas como pendientes en `mitdb_eval/INFORME_METODOLOGICO.md`: frecuencia de muestreo efectiva/jitter, latencia extremo a extremo, pérdida de paquetes/reconexión, CPU/memoria, y el modo de doble detección por onda T.

**No requiere modificar el detector ni sus parámetros.** Solo mide lo que el detector ya hace en hardware real.

## Qué se instrumentó (ya en `backend/backend_iot.py`, opt-in, sin efecto si no se activa)

- `ECG_DIAG_LOG_PATH`: si se define, registra el timestamp monotónico de cada muestra cruda a un CSV (para medir Fs efectiva y jitter). Vacío por defecto = sin efecto.
- El WebSocket `/ws/ecg` ahora incluye `seq` (contador por conexión), `server_sent_at` y `sample_acquired_at` en cada mensaje — necesario para medir latencia, huecos y reconexión desde un cliente externo.
- `GET /system/status` ya existía (CPU%, RAM%, temperatura, uptime) — no se tocó, solo se reutiliza.

## Requisitos

- En la Raspberry Pi: el backend corriendo normalmente (`backend/`), más `pip install -r pi_diagnostics/requirements.txt` en el mismo entorno si vas a correr `monitor_resources.py` ahí.
- En una laptop en la misma red que la Pi (para el cliente de latencia, que debe medir lo que un cliente real experimenta, no lo que ve la propia Pi): `pip install -r pi_diagnostics/requirements.txt`.
- La IP de la Pi en su red (o el access point `MEDINIC-ECG`) y el `ECG_API_KEY` configurado (por defecto `devkey-123` si no se cambió).

## Paso 1 — Arranque sin errores de ADC/I²C (punto 1 del deployment gate)

Enciende la Pi con el sensor conectado y un usuario con electrodos puestos. Revisa los logs del backend (o `GET /health`) durante 2-3 minutos: confirma `hw_ok: true`, sin `hw_error`, sin reinicios del hilo de adquisición. Si aparece cualquier error de I²C, documenta el mensaje exacto antes de seguir — los pasos siguientes no tienen sentido con el hardware fallando.

## Paso 2 — Frecuencia efectiva y jitter (puntos 1-2)

En la Pi, arranca el backend con el logger de diagnóstico activado, durante una sesión de **al menos 30 minutos** con un participante conectado (o el sensor en modo de prueba, pero con adquisición real, no `ECG_DEMO_LOOP`):

```bash
export ECG_DEMO_LOOP=0
export ECG_DIAG_LOG_PATH=/home/pi/diag_samples.csv
python backend_iot.py   # o el comando/servicio que ya usan para arrancarlo
```

Al terminar la sesión, copia `diag_samples.csv` a donde vayas a analizar (puede ser la misma Pi) y corre:

```bash
python pi_diagnostics/fs_jitter_report.py --in diag_samples.csv --out results/fs_jitter_report.json --configured-rate-hz 250
```

Esto da Fs efectiva (media/mediana), jitter (SD del intervalo entre muestras), percentiles, y una estimación de muestras perdidas por cada hueco detectado.

## Paso 3 — Latencia extremo a extremo, pérdida de paquetes, reconexión (punto 3 parcial + limitación abierta)

Desde la **laptop**, con el backend de la Pi corriendo y transmitiendo por WebSocket:

```bash
python pi_diagnostics/ws_latency_client.py --host <IP_DE_LA_PI> --port 8000 \
    --api-key devkey-123 --duration-s 1800 --out results/ws_latency_normal.csv
```

Para probar explícitamente el comportamiento de reconexión (fuerza un cierre y reconexión cada 5 minutos):

```bash
python pi_diagnostics/ws_latency_client.py --host <IP_DE_LA_PI> --port 8000 \
    --api-key devkey-123 --duration-s 1800 --reconnect-every-s 300 \
    --out results/ws_latency_reconnect.csv
```

**Importante sobre la latencia servidor→cliente que reporta este script:** solo es correcta si los relojes de la Pi y la laptop están sincronizados (NTP en ambas). Sin eso, confía en el **jitter entre llegadas** (no necesita sincronización) y en los **huecos de secuencia**/reconexiones, que sí son confiables sin sincronizar relojes.

## Paso 4 — CPU, memoria, temperatura (punto 4)

En paralelo al paso 3 (misma ventana de tiempo), en la Pi o remotamente:

```bash
python pi_diagnostics/monitor_resources.py --host <IP_DE_LA_PI> --port 8000 \
    --api-key devkey-123 --duration-s 1800 --interval-s 2 --out results/resources.csv
```

Revisa especialmente la temperatura: por encima de ~80°C la Raspberry Pi 4 puede activar *throttling* térmico, lo que afectaría la Fs efectiva medida en el paso 2 — si ves temperaturas altas, correlaciona con `windowed_fs_10s_bins` de `fs_jitter_report.json` para ver si hay caída de Fs hacia el final de la sesión.

## Paso 5 — Modo de doble detección por onda T (punto 5)

Ya lo validé de forma offline con el registro 113 de MIT-BIH (ver `mitdb_eval/results/final_48/twave_mode_record113.json`): **el conteo de picos válidos vs. crudos NO es un indicador confiable** de este modo — el filtro de validación de RR deja pasar casi todos los picos espurios porque le basta con que UNO de los dos intervalos vecinos parezca válido. La señal confiable es la fracción de picos crudos separados 150-450 ms del anterior, y en la práctica el síntoma observable en vivo sería un `hr_median` cercano al doble del real.

En hardware:
1. Graba una sesión de un participante con ondas T visiblemente altas/picudas en el monitor.
2. Exporta la sesión (ZIP con `.dat`).
3. Corre:

```bash
python pi_diagnostics/check_twave_mode.py --dat <SESSION_ID>.dat --fs 250 --out results/twave_check.json
```

4. Si el veredicto indica el patrón presente, compara `hr_median` de esa sesión contra un pulso manual tomado al mismo tiempo.

## Paso 6 — Reporte combinado

Con `results/fs_jitter_report.json`, `results/ws_latency_*.csv` (+ `.summary.json`), `results/resources.csv` y `results/twave_check.json` en la misma carpeta:

```bash
python pi_diagnostics/analyze_all.py --results-dir results --out results/PI_VALIDATION_REPORT.md
```

Esto genera un solo Markdown con los 5 puntos del deployment gate respondidos con números reales. Ese archivo es lo que hay que revisar antes de decidir si este backend reemplaza el que está en producción, y es la base para completar la sección de caracterización de hardware del paper.

## Qué esto NO mide (sigue como limitación, sé explícito en el paper)

- Latencia real de renderizado en el navegador (solo mide hasta que el mensaje llega al cliente Python, no hasta que se pinta en pantalla).
- Precisión de la adquisición analógica (AD8232, RC de entrada) — esto es jitter/Fs/latencia del *pipeline digital*, no del front-end analógico.
- Seguridad eléctrica, capacidad de batería en mAh, aprobación ética — no se tocan aquí, siguen pendientes.
- El modo de doble detección por onda T en Paso 5 depende de que el participante grabado realmente tenga esa morfología; si el veredicto sale negativo en una sesión, no descarta el modo, solo dice que esa sesión no lo mostró.
