export function About() {
  return (
    <section id="about" className="py-20 bg-slate-950 text-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center space-y-6">
          <h2 className="text-4xl font-bold mb-6 text-emerald-400">
            Que es Medinic?
          </h2>
          <p className="text-xl text-slate-300 leading-relaxed">
            Medinic es una plataforma de monitoreo cardiovascular que integra dispositivos biomedicos,
            adquisicion de senal ECG y notificaciones en tiempo real para apoyar pruebas de
            investigacion y prototipado clinico.
          </p>

          <div className="grid md:grid-cols-2 gap-6 pt-8 text-left">
            <div className="flex gap-3 items-start">
              <p className="text-slate-200 font-medium">Funciona con sensores AD8232 y Raspberry Pi 4.</p>
            </div>

            <div className="flex gap-3 items-start">
              <p className="text-slate-200 font-medium">Procesa la senal ECG y calcula metricas de monitoreo.</p>
            </div>

            <div className="flex gap-3 items-start">
              <p className="text-slate-200 font-medium">Genera alertas del sistema ante eventos de adquisicion o sensor.</p>
            </div>

            <div className="flex gap-3 items-start">
              <p className="text-slate-200 font-medium">Permite revisar historial, HRV y reportes de sesiones.</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
