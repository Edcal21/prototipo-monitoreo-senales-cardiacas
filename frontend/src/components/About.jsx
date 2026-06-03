export const About = () => (
  <section
    id="about"
    className="relative overflow-hidden border-y border-slate-800 bg-slate-950 py-24 text-white"
  >
    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(16,185,129,0.12),transparent_24%),radial-gradient(circle_at_85%_30%,rgba(56,189,248,0.12),transparent_22%)]" />

    <div className="relative mx-auto grid max-w-7xl gap-12 px-6 md:grid-cols-[1.1fr_0.9fr] md:px-10">
      <div>
        <span className="inline-flex items-center rounded-full border border-emerald-500/20 bg-emerald-500/10 px-4 py-1 text-xs font-bold uppercase tracking-[0.22em] text-emerald-300">
          Sobre Medinic
        </span>

        <h2 className="mt-6 max-w-3xl text-4xl font-black leading-tight text-white md:text-5xl">
          Tecnologia biomedica aplicada al monitoreo cardiaco en tiempo real
        </h2>

        <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
          Medinic es una plataforma IoT desarrollada para adquirir, procesar y
          visualizar senales electrocardiograficas en tiempo real mediante
          <span className="font-semibold text-white"> Raspberry Pi 4</span>,
          <span className="font-semibold text-white"> ADS1115</span> y un backend
          orientado a streaming clinico.
        </p>

        <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-400">
          El sistema integra transmision por WebSocket, analisis de metricas como
          BPM, RMSSD y SDNN, ademas de una base preparada para validacion
          experimental y mejora continua del procesamiento de senal.
        </p>

        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">
              Hardware
            </div>
            <div className="mt-2 text-sm font-semibold text-white">Raspberry Pi + ADS1115</div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">
              Backend
            </div>
            <div className="mt-2 text-sm font-semibold text-white">FastAPI + WebSocket</div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">
              Analisis
            </div>
            <div className="mt-2 text-sm font-semibold text-white">HR, HRV y monitoreo continuo</div>
          </div>
        </div>
      </div>

      <div className="rounded-[2rem] border border-slate-800 bg-slate-900/75 p-8 shadow-2xl shadow-slate-950/30">
        <div className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-300">
          Objetivo del proyecto
        </div>

        <h3 className="mt-4 text-2xl font-bold text-white">
          Construir una plataforma ECG funcional, escalable y lista para validacion experimental
        </h3>

        <ul className="mt-8 space-y-4 text-slate-300">
          <li className="rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-3">
            Monitoreo continuo de senal ECG en tiempo real.
          </li>
          <li className="rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-3">
            Procesamiento digital sobre arquitectura edge computing.
          </li>
          <li className="rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-3">
            Calculo de metricas fisiologicas y variabilidad cardiaca.
          </li>
          <li className="rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-3">
            Base tecnologica para investigacion biomedica y validacion experimental.
          </li>
        </ul>
      </div>
    </div>
  </section>
);
