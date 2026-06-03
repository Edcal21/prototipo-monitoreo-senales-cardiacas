# MEDINIC ECG

Plataforma biomédica para adquisición, visualización, análisis y exportación de señales ECG en tiempo real sobre Raspberry Pi.

Este repositorio contiene el backend de adquisición/procesamiento y el frontend web del monitor ECG utilizado en el prototipo MEDINIC. El sistema integra Raspberry Pi 4, ADS1115, módulo AD8232, FastAPI, WebSocket y una interfaz React/Vite para monitoreo, registro de sesiones y exportación de archivos estilo PhysioNet.

> Este proyecto es un prototipo académico/de investigación. No corresponde a un dispositivo médico certificado ni debe usarse como herramienta de diagnóstico clínico formal.

## Características principales

- Adquisición ECG desde ADS1115 en modo single-ended.
- Visualización web en tiempo real mediante WebSocket.
- Procesamiento digital de señal ECG.
- Filtrado pasa banda y notch digital cuando la frecuencia de muestreo lo permite.
- Detección de picos R y cálculo de métricas cardíacas.
- Validación de consistencia entre BPM, picos R y duración efectiva del análisis.
- Gestión de pacientes y sesiones.
- Usuarios administradores y usuarios de solo lectura.
- Bloqueo de grabación para perfiles de solo lectura.
- Exportación por sesión en ZIP con archivos `.dat`, `.hea`, `.atr`, `.json` y gráficas PNG.
- Exportación PDF y Excel desde el backend.
- Lectura de porcentaje de batería mediante divisor resistivo al canal A1 del ADS1115.
- Script de apoyo "modo profesor" para explicar etapas de adquisición y procesamiento en vivo.
- Script opcional para reinicio por botón físico conectado a GPIO.

## Estructura del repositorio

```text
medinic-ecg-repo/
├── backend/
│   ├── backend_iot.py           # API FastAPI, WebSocket, adquisición y exportaciones
│   ├── postprocess_ecg.py       # Filtrado, picos R, RR, BPM, HRV y calidad
│   ├── patient_store.py         # Persistencia SQLite de pacientes
│   ├── session_store.py         # Persistencia SQLite de sesiones
│   ├── ecg_live_professor.py    # Script didáctico para observar etapas en vivo
│   ├── gpio_reboot_button.py    # Reinicio por botón físico GPIO5
│   ├── ecg_postprocess.py       # Postproceso visual opcional de imágenes ECG
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── components/
    │   │   └── ECGMonitor.tsx   # Monitor ECG principal
    │   └── contexts/
    │       └── AuthContext.jsx  # Login y headers de autenticación
    ├── package.json
    ├── package-lock.json
    ├── vite.config.js
    └── index.html
```

## Arquitectura general

```text
Electrodos
   │
AD8232
   │ salida analogica
   ▼
ADS1115 canal A0
   │ I2C
   ▼
Raspberry Pi 4
   │
FastAPI + WebSocket
   │
React/Vite Frontend
```

El canal A0 del ADS1115 se utiliza para la señal ECG. El canal A1 se utiliza para medir el voltaje del banco de batería mediante un divisor resistivo.

## Hardware usado

- Raspberry Pi 4.
- ADS1115 de 16 bits por I2C.
- AD8232 como front-end analógico ECG.
- Electrodos ECG.
- Divisor resistivo para medición de batería.
- Botón físico opcional para reinicio.

### Conexión ADS1115

El ADS1115 se usa por I2C:

- SDA: GPIO2.
- SCL: GPIO3.
- Dirección I2C típica: `0x48`.
- Canal A0: señal ECG.
- Canal A1: lectura de batería.

El modo usado es single-ended: cada canal mide el voltaje respecto a GND.

### Conexión AD8232

Configuración usada por el prototipo:

- OUT del AD8232 hacia A0 del ADS1115.
- LO+ hacia GPIO17.
- LO- hacia GPIO27.
- SDN hacia GPIO26.
- GND común entre AD8232, ADS1115 y Raspberry Pi.

### Lectura de batería

La batería se mide mediante divisor resistivo conectado al canal A1 del ADS1115.

Valores documentados:

```text
R1 = 100 kOhm
R2 = 42 kOhm
```

La fórmula usada es:

```text
Vbat = Vadc * (R1 + R2) / R2
```

El porcentaje se estima entre:

```text
0%   = 4.4 V
100% = 5.0 V
```

Valores superiores a 5.0 V se limitan a 100% para evitar porcentajes imposibles cuando se usa una fuente o banco de batería con mayor voltaje.

## Procesamiento ECG

El módulo `postprocess_ecg.py` realiza el procesamiento principal:

- Filtrado notch de 60 Hz si la frecuencia efectiva lo permite.
- Filtrado Butterworth pasa banda.
- Detección de picos R.
- Cálculo de intervalos RR.
- Validación fisiológica de RR:
  - RR mínimo: 300 ms.
  - RR máximo: 2000 ms.
- Rechazo de detecciones aisladas por ruido.
- Cálculo de BPM a partir de RR válidos.
- Cálculo de RMSSD a partir de RR válidos.
- Advertencias cuando BPM, picos R o RMSSD no son coherentes.

El cálculo de RMSSD se basa en:

```text
RMSSD = sqrt(mean(diff(RR)^2))
```

## Usuarios

El backend soporta autenticación por API key, usuario/contraseña y Basic Auth.

Usuario administrador local:

```text
admin / admin123
```

Usuarios de solo lectura configurados:

```text
fernando.flores / medinic2026
jaime.alvarez   / medinic2026
imer.diaz       / medinic2026
```

Los usuarios de solo lectura pueden consultar y visualizar, pero no pueden iniciar ni detener grabaciones ECG.

## Instalación del backend en Raspberry Pi

Desde la Raspberry Pi:

```bash
cd ~/mi-landing/mi-proyecto-ecg/Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Arranque manual:

```bash
python -m uvicorn backend_iot:app --host 0.0.0.0 --port 8000
```

Arranque en segundo plano:

```bash
nohup python -m uvicorn backend_iot:app --host 0.0.0.0 --port 8000 > logs/uvicorn_manual.log 2>&1 &
```

Verificación:

```bash
curl http://127.0.0.1:8000/health
```

## Instalación del frontend

Desde la carpeta `frontend`:

```bash
npm install
npm run build
```

Para desarrollo:

```bash
npm run dev
```

La interfaz espera encontrar el backend en el mismo host, puerto `8000`:

```text
http://<ip-del-dispositivo>:8000
```

## Endpoints principales

```text
GET  /health
GET  /system/status
POST /auth/login
GET  /users/me
POST /patients
GET  /patients
POST /sessions/start
POST /sessions/stop/{session_id}
GET  /sessions
GET  /sessions/report.pdf/{session_id}
GET  /sessions/export.xlsx
GET  /sessions/export.zip/{session_id}
WS   /ws/ecg
```

## Exportación de sesiones

Cada sesión se puede exportar como paquete ZIP desde el frontend o desde el endpoint:

```bash
curl -L -o ECG.zip \
  "http://127.0.0.1:8000/sessions/export.zip/<session_id>" \
  -H "x-api-key: devkey-123"
```

El ZIP contiene:

```text
ECG-xxxxx.dat
ECG-xxxxx.hea
ECG-xxxxx.atr
ECG-xxxxx.json
ECG-xxxxx_clinical.png
ECG-xxxxx_qrs_zoom.png
```

## Modo profesor

El script `ecg_live_professor.py` permite observar en terminal las etapas del procesamiento en vivo:

```bash
cd backend
source venv/bin/activate
python ecg_live_professor.py --api-key devkey-123
```

Muestra:

- adquisición
- línea base
- corrección/filtrado
- detección de picos R
- RR
- BPM
- métricas reportadas por backend

## Botón físico de reinicio

El script `gpio_reboot_button.py` permite reiniciar la Raspberry Pi con un botón en GPIO5.

Conexión sugerida:

```text
GPIO5  -> botón -> GND
```

Ejecución:

```bash
python gpio_reboot_button.py
```

Mantener el botón presionado durante 2 segundos ejecuta:

```bash
sudo /sbin/reboot
```

## Notas de defensa técnica

El sistema diferencia entre:

- `ADC data rate`: configuración nominal del ADS1115, por ejemplo 250 SPS.
- `Frecuencia de muestreo`: frecuencia efectiva estimada por software según timestamps reales de adquisición.

Esto permite documentar de forma transparente que el ADC puede estar configurado a 250 SPS, aunque la frecuencia efectiva del sistema completo pueda ser menor por I2C, Python, carga del sistema, procesamiento y WebSocket.

## Limitaciones

- No es un dispositivo médico certificado.
- La calidad de señal depende de electrodos, contacto, movimiento, alimentación y ruido ambiental.
- El ADS1115 por I2C y Python pueden limitar la frecuencia efectiva sostenida.
- El análisis se orienta a monitoreo, validación académica y prototipado.

## Mejoras futuras

- Optimizar adquisición con lectura bufferizada.
- Separar adquisición, procesamiento y WebSocket en procesos independientes.
- Mantener 250 Hz efectivos de extremo a extremo.
- Integrar calibración de amplitud con señal patrón.
- Exportar archivos WFDB binarios compatibles estrictamente con PhysioNet.
- Agregar pruebas automatizadas para métricas ECG.

## Licencia

Proyecto académico. Definir licencia antes de publicación final si el repositorio será público.
