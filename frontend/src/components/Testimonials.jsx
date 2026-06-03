export const Testimonials = () => (
  <section className="relative overflow-hidden bg-slate-950 py-24 text-white">
    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(16,185,129,0.10),transparent_24%),radial-gradient(circle_at_85%_25%,rgba(56,189,248,0.10),transparent_22%)]" />

    <div className="relative mx-auto max-w-7xl px-6 md:px-10">
      <div className="mx-auto max-w-3xl text-center">
        <p className="inline-flex items-center rounded-full border border-emerald-500/20 bg-emerald-500/10 px-4 py-1 text-xs font-bold uppercase tracking-[0.22em] text-emerald-300">
          Validacion y enfoque
        </p>

        <h2 className="mt-6 text-4xl font-black tracking-tight text-white md:text-5xl">
          Vision tecnica y biomedica del proyecto
        </h2>

        <p className="mt-5 text-lg leading-8 text-slate-300">
          Medinic fue concebido con una logica de ingenieria aplicada a monitoreo clinico:
          claridad visual, estabilidad del sistema y utilidad real para pruebas,
          prototipos e investigacion.
        </p>
      </div>

      <div className="mt-14 grid gap-6 md:grid-cols-3">
        <div className="rounded-[1.75rem] border border-slate-800 bg-slate-900/70 p-8 shadow-2xl shadow-slate-950/20">
          <div className="text-4xl leading-none text-emerald-300">"</div>
          <p className="mt-4 text-base leading-8 text-slate-300">
            La interfaz prioriza lo esencial y mantiene una lectura limpia de la
            senal. Se siente orientada a monitoreo en tiempo real, no a una demo
            visual generica.
          </p>

          <div className="mt-8 border-t border-slate-800 pt-5">
            <p className="font-semibold text-white">Revision tecnica</p>
            <p className="text-sm text-slate-400">Enfoque UX biomedico</p>
          </div>
        </div>

        <div className="rounded-[1.75rem] border border-slate-800 bg-slate-900/70 p-8 shadow-2xl shadow-slate-950/20">
          <div className="text-4xl leading-none text-sky-300">"</div>
          <p className="mt-4 text-base leading-8 text-slate-300">
            La combinacion de edge computing, adquisicion embebida y streaming por
            WebSocket proyecta una arquitectura realista y tecnicamente coherente
            para un sistema IoT biomedico.
          </p>

          <div className="mt-8 border-t border-slate-800 pt-5">
            <p className="font-semibold text-white">Evaluacion de arquitectura</p>
            <p className="text-sm text-slate-400">IoT + Backend + tiempo real</p>
          </div>
        </div>

        <div className="rounded-[1.75rem] border border-slate-800 bg-slate-900/70 p-8 shadow-2xl shadow-slate-950/20">
          <div className="text-4xl leading-none text-amber-300">"</div>
          <p className="mt-4 text-base leading-8 text-slate-300">
            El valor del proyecto esta en integrar senal ECG, metricas HR/HRV y una
            base tecnologica preparada para evolucionar hacia validacion experimental
            y mejora del procesamiento de senal.
          </p>

          <div className="mt-8 border-t border-slate-800 pt-5">
            <p className="font-semibold text-white">Observacion academica</p>
            <p className="text-sm text-slate-400">Senal, metricas y proyeccion clinica</p>
          </div>
        </div>
      </div>
    </div>
  </section>
);
