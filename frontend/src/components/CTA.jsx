export const CTA = ({ onAction }) => (
  <section className="relative overflow-hidden border-t border-slate-800 bg-slate-950 py-24 text-white">
    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(16,185,129,0.14),transparent_26%)]" />

    <div className="relative mx-auto max-w-5xl px-6 text-center md:px-10">
      <div className="rounded-[2rem] border border-slate-800 bg-slate-900/70 px-8 py-14 shadow-2xl shadow-slate-950/30">
        <p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-300">
          Siguiente paso
        </p>

        <h2 className="mt-5 text-4xl font-black tracking-tight text-white md:text-5xl">
          Explora el monitor ECG y la arquitectura de Medinic
        </h2>

        <p className="mx-auto mt-5 max-w-2xl text-lg leading-8 text-slate-300">
          Accede al entorno de monitoreo en tiempo real y conoce una plataforma
          diseñada para adquisición biomédica, análisis local de señal y validación experimental.
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <button
            onClick={onAction}
            className="rounded-2xl bg-emerald-400 px-7 py-3.5 text-sm font-black uppercase tracking-wide text-slate-950 shadow-[0_18px_50px_rgba(16,185,129,0.22)] transition hover:bg-emerald-300"
          >
            Ir al monitor
          </button>

          <a
            href="#about"
            className="rounded-2xl border border-slate-700 bg-slate-900/50 px-7 py-3.5 text-sm font-bold uppercase tracking-wide text-slate-100 transition hover:border-slate-500 hover:bg-slate-800/70"
          >
            Revisar proyecto
          </a>
        </div>
      </div>
    </div>
  </section>
);
