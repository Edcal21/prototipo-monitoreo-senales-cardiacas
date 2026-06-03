import { LoginForm } from "./LoginForm.tsx";

export const AuthPage = ({ onBack }) => (
  <div className="min-h-screen bg-slate-950 text-white flex flex-col">
    {/* Barra superior simple */}
    <div className="px-6 py-4">
      <button
        onClick={onBack}
        className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-900"
      >
        ← Volver
      </button>
    </div>

    {/* Formulario */}
    <div className="flex-1 flex items-center justify-center px-6 pb-10">
      <LoginForm />
    </div>
  </div>
);
