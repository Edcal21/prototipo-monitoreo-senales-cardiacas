/**
 * Figma-like "Connect Device" button.
 *
 * - Full-width pill bar
 * - Soft red glow + subtle gradient
 * - Crisp border and blur layer
 */
import React from "react";
import { Plug } from "lucide-react";

type Props = {
  onClick?: () => void;
  disabled?: boolean;
  state: "disconnected" | "connecting" | "connected";
  className?: string;
};

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function ConnectDeviceButton({ onClick, disabled, state, className }: Props) {
  const isDisconnected = state === "disconnected";
  const isConnecting = state === "connecting";
  const isConnected = state === "connected";

  const label = isDisconnected
    ? "Conectar Dispositivo"
    : isConnecting
    ? "Conectando..."
    : "Dispositivo Conectado";

  const dotClass = isDisconnected
    ? "bg-red-500 shadow-[0_0_14px_rgba(239,68,68,0.85)]"
    : isConnecting
    ? "bg-amber-400 shadow-[0_0_14px_rgba(251,191,36,0.75)]"
    : "bg-emerald-400 shadow-[0_0_14px_rgba(52,211,153,0.75)]";

  const frameClass = isDisconnected
    ? "border-red-500/25 from-red-500/18 via-red-500/10 to-red-500/18 text-red-200"
    : isConnecting
    ? "border-amber-500/25 from-amber-500/18 via-amber-500/10 to-amber-500/18 text-amber-200"
    : "border-emerald-500/25 from-emerald-500/18 via-emerald-500/10 to-emerald-500/18 text-emerald-200";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "relative w-full md:w-72 h-12 rounded-2xl border",
        "bg-gradient-to-r backdrop-blur-sm",
        "shadow-[0_0_0_1px_rgba(148,163,184,0.06),0_18px_40px_rgba(0,0,0,0.45)]",
        "transition active:scale-[0.99]",
        !disabled && "hover:brightness-110",
        disabled && "opacity-75 cursor-not-allowed",
        frameClass,
        className
      )}
    >
      <span className="absolute inset-0 rounded-2xl bg-white/[0.03] pointer-events-none" />
      <span className="relative flex items-center justify-center gap-2 text-sm font-semibold">
        <span className={cx("inline-block h-2.5 w-2.5 rounded-full", dotClass)} />
        <Plug size={16} className="opacity-80" />
        <span>{label}</span>
      </span>
    </button>
  );
}
