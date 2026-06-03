export const Services = () => (
  <section className="py-16 bg-white">
    <div className="max-w-6xl mx-auto px-4 grid grid-cols-1 md:grid-cols-3 gap-8">
      <div className="p-6 border rounded-xl hover:shadow-md transition-shadow text-center">
        <h3 className="font-bold text-xl mb-2">Monitoreo Real</h3>
        <p className="text-slate-600">Visualización instantánea de la señal eléctrica cardíaca.</p>
      </div>
      <div className="p-6 border rounded-xl hover:shadow-md transition-shadow text-center">
        <h3 className="font-bold text-xl mb-2">Análisis de Datos</h3>
        <p className="text-slate-600">Cálculo de métricas como BPM y variabilidad (HRV).</p>
      </div>
      <div className="p-6 border rounded-xl hover:shadow-md transition-shadow text-center">
        <h3 className="font-bold text-xl mb-2">Alertas del Sistema</h3>
        <p className="text-slate-600">Notificaciones automáticas ante arritmias o fallos de sensor.</p>
      </div>
    </div>
  </section>
);
