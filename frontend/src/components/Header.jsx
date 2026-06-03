export const Header = ({ onAdminClick, onECGClick }) => (
  <header className="sticky top-0 z-50 bg-white/80 backdrop-blur border-b border-slate-200">
    <div className="mx-auto max-w-6xl px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="h-9 w-9 rounded-xl bg-slate-900 text-white flex items-center justify-center font-bold">
          ♥
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight text-slate-900">MEDINIC</div>
          <div className="text-xs text-slate-500">ECG en tiempo real</div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={onECGClick}
          className="rounded-xl bg-sky-500 hover:bg-sky-400 text-white font-semibold px-4 py-2 transition"
        >
          Monitor ECG
        </button>

        <button
          onClick={onAdminClick}
          className="rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-semibold px-4 py-2 transition"
        >
          Ingresar como doctor
        </button>
      </div>
    </div>
  </header>
);
