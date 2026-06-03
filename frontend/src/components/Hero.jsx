export const Hero = ({ onMonitorClick }) => (
  <section className="relative overflow-hidden border-b border-slate-800 bg-slate-950 text-white">
    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(16,185,129,0.18),_transparent_26%),radial-gradient(circle_at_80%_18%,_rgba(56,189,248,0.16),_transparent_22%),linear-gradient(to_bottom,_#020617,_#0f172a_50%,_#020617)]" />
    <div className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(rgba(148,163,184,0.14)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.14)_1px,transparent_1px)] [background-size:28px_28px]" />
    <div className="pointer-events-none absolute -left-24 top-24 h-72 w-72 rounded-full bg-emerald-500/12 blur-3xl" />
    <div className="pointer-events-none absolute right-[-80px] top-10 h-80 w-80 rounded-full bg-sky-500/12 blur-3xl" />
    <div className="pointer-events-none absolute bottom-[-140px] left-1/2 h-80 w-[36rem] -translate-x-1/2 rounded-full bg-cyan-400/8 blur-3xl" />

    <div className="relative mx-auto grid min-h-[88vh] max-w-7xl items-center gap-14 px-6 py-16 md:grid-cols-[1.1fr_0.9fr] md:px-10 md:py-24">
      <div className="max-w-3xl">
        <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.24em] text-emerald-300">
          <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.9)]" />
          Monitoreo ECG en tiempo real
        </div>

        <h1 className="mt-8 max-w-4xl text-4xl font-black leading-[0.95] tracking-tight text-white md:text-6xl xl:text-7xl">
          MEDINIC
          <span className="mt-3 block text-2xl font-semibold leading-tight text-slate-300 md:text-4xl">
            Plataforma biomédica para adquisición, análisis y visualización de ECG en tiempo real
          </span>
        </h1>

        <p className="mt-8 max-w-2xl text-base leading-8 text-slate-300 md:text-lg">
          Un sistema IoT orientado a investigación y prototipado clínico que integra
          <span className="font-semibold text-white"> Raspberry Pi 4</span>,
          <span className="font-semibold text-white"> ADS1115</span>,
          <span className="font-semibold text-white"> FastAPI</span>,
          <span className="font-semibold text-white"> WebSocket</span> y procesamiento local de señal ECG.
        </p>

        <div className="mt-10 flex flex-wrap items-center gap-4">
          <button
            onClick={onMonitorClick}
            className="rounded-2xl bg-emerald-400 px-7 py-3.5 text-sm font-black uppercase tracking-wide text-slate-950 shadow-[0_18px_50px_rgba(16,185,129,0.22)] transition hover:bg-emerald-300"
          >
            Abrir monitor ECG
          </button>

          <a
            href="#about"
            className="rounded-2xl border border-slate-700 bg-slate-900/50 px-7 py-3.5 text-sm font-bold uppercase tracking-wide text-slate-100 transition hover:border-slate-500 hover:bg-slate-800/70"
          >
            Ver arquitectura
          </a>
        </div>

        <div className="mt-12 grid gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/55 px-4 py-4 shadow-xl shadow-slate-950/20">
            <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">Streaming</div>
            <div className="mt-2 text-sm font-semibold text-white">WebSocket en vivo</div>
            <div className="mt-1 text-sm text-slate-400">Visualización continua de señal y métricas.</div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/55 px-4 py-4 shadow-xl shadow-slate-950/20">
            <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">Procesamiento</div>
            <div className="mt-2 text-sm font-semibold text-white">HR y HRV local</div>
            <div className="mt-1 text-sm text-slate-400">BPM, RMSSD, SDNN y análisis sobre edge node.</div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/55 px-4 py-4 shadow-xl shadow-slate-950/20">
            <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">Despliegue</div>
            <div className="mt-2 text-sm font-semibold text-white">Raspberry Pi 4</div>
            <div className="mt-1 text-sm text-slate-400">Diseñado para operación embebida y validación experimental.</div>
          </div>
        </div>
      </div>

      <div className="relative">
        <div className="absolute -inset-4 rounded-[2rem] bg-gradient-to-br from-emerald-500/10 via-sky-500/10 to-transparent blur-2xl" />
        <div className="relative rounded-[2rem] border border-slate-800 bg-slate-900/75 p-5 shadow-2xl shadow-slate-950/40 backdrop-blur">
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-300">Vista clínica</div>
              <div className="mt-1 text-lg font-semibold text-white">Monitor ECG embebido</div>
            </div>
            <div className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300">
              online
            </div>
          </div>

          <div className="mt-5 space-y-4">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
              <div className="mb-3 flex items-center justify-between text-xs text-slate-400">
                <span>Señal ECG</span>
                <span>25 mm/s · 10 mm/mV</span>
              </div>
              <div className="h-36 rounded-xl border border-slate-800 bg-[linear-gradient(to_bottom,rgba(2,6,23,0.82),rgba(15,23,42,0.96))] p-2">
                <div className="h-full w-full opacity-80 [background-image:linear-gradient(rgba(148,163,184,0.12)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.12)_1px,transparent_1px)] [background-size:18px_18px]">
                  <svg viewBox="0 0 400 120" className="h-full w-full">
                    <path
                      d="M0,68 L18,68 L28,62 L40,70 L62,69 L78,72 L95,70 L110,66 L128,69 L145,68 L160,50 L171,44 L186,70 L205,71 L220,69 L240,68 L255,70 L268,67 L285,45 L298,82 L315,70 L332,68 L350,69 L368,66 L384,68 L400,67"
                      fill="none"
                      stroke="rgb(52 211 153)"
                      strokeWidth="2.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-500">BPM</div>
                <div className="mt-2 text-3xl font-black text-white">78</div>
                <div className="mt-1 text-xs text-emerald-300">ritmo estable</div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-500">RMSSD</div>
                <div className="mt-2 text-3xl font-black text-white">41</div>
                <div className="mt-1 text-xs text-sky-300">variabilidad detectada</div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-500">Estado</div>
                <div className="mt-2 text-lg font-black text-white">Backend ECG</div>
                <div className="mt-1 text-xs text-amber-300">streaming disponible</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
);
