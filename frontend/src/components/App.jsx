// src/components/App.jsx
import { useState } from "react";
import { AuthProvider, useAuth } from "../contexts/AuthContext";

import { Hero } from "./Hero";
import { About } from "./About";
import { Services } from "./Services";
import { Features } from "./Features";
import { Testimonials } from "./Testimonials";
import { Footer } from "./Footer";
import { AuthPage } from "./AuthPage";
import { ECGMonitor } from "./ECGMonitor";
import { Toaster } from "sonner";

import { AnimatePresence, motion } from "framer-motion";

const pageMotion = {
  initial: { opacity: 0, y: 20, scale: 0.99 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: -12, scale: 1.01 },
};

const pageTransition = {
  duration: 0.45,
  ease: [0.22, 1, 0.36, 1],
};

function PageWrapper({ children, pageKey, className = "" }) {
  return (
    <motion.div
      key={pageKey}
      variants={pageMotion}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={pageTransition}
      className={`min-h-screen w-full ${className}`}
    >
      {children}
    </motion.div>
  );
}

function AppBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-slate-950">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(16,185,129,0.16),_transparent_30%),radial-gradient(circle_at_80%_20%,_rgba(56,189,248,0.12),_transparent_24%),linear-gradient(to_bottom,_#020617,_#0f172a_45%,_#020617)]" />
      <div className="absolute inset-0 opacity-[0.06] [background-image:linear-gradient(rgba(148,163,184,0.15)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.15)_1px,transparent_1px)] [background-size:32px_32px]" />
      <div className="absolute left-[-8rem] top-24 h-72 w-72 rounded-full bg-emerald-500/10 blur-3xl" />
      <div className="absolute bottom-[-6rem] right-[-4rem] h-80 w-80 rounded-full bg-sky-500/10 blur-3xl" />
    </div>
  );
}

function LandingPage({ onMonitorClick }) {
  return (
    <PageWrapper pageKey="landing" className="text-white">
      <main className="relative">
        <Hero onMonitorClick={onMonitorClick} />
        <About />
        <Services />
        <Features />
        <Testimonials />
      </main>
      <Footer />
    </PageWrapper>
  );
}

function AppContent() {
  const { isAuthenticated } = useAuth();
  const [showAuth, setShowAuth] = useState(false);
  const [showECGMonitor, setShowECGMonitor] = useState(false);

  const openAuth = () => setShowAuth(true);
  const closeAuth = () => setShowAuth(false);

  const goBackFromMonitor = () => {
    setShowECGMonitor(false);
    setShowAuth(false);
  };

  return (
    <div className="relative min-h-screen overflow-x-hidden selection:bg-emerald-300 selection:text-slate-950">
      <AppBackground />

      <AnimatePresence mode="wait">
        {showECGMonitor || isAuthenticated ? (
          <PageWrapper pageKey="monitor">
            <ECGMonitor onBack={goBackFromMonitor} />
          </PageWrapper>
        ) : showAuth ? (
          <PageWrapper pageKey="auth">
            <AuthPage onBack={closeAuth} />
          </PageWrapper>
        ) : (
          <LandingPage onMonitorClick={openAuth} />
        )}
      </AnimatePresence>

      <Toaster
        position="top-right"
        richColors
        closeButton
        toastOptions={{
          classNames: {
            toast: "!border !border-slate-700 !bg-slate-900 !text-slate-100",
            title: "!text-slate-50",
            description: "!text-slate-300",
          },
        }}
      />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
