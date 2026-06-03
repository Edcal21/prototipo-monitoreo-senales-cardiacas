export const Features = () => (
  <section className="py-16 bg-slate-900 text-white">
    <div className="max-w-6xl mx-auto px-4">
      <h2 className="text-3xl font-bold text-center mb-12">Tecnología de Vanguardia</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
        <div className="flex gap-4 italic">
          <span className="text-emerald-400 font-bold">✓</span>
          <p>Baja latencia en la transmisión ADS1115 → Raspberry Pi 4.</p>
        </div>
        <div className="flex gap-4 italic">
          <span className="text-emerald-400 font-bold">✓</span>
          <p>Filtros digitales avanzados para eliminar ruido de 60Hz.</p>
        </div>
      </div>
    </div>
  </section>
);
