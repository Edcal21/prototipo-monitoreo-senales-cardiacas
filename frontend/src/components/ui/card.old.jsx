export const Card = ({ children, className }) => (
  <div className={`rounded-xl border border-slate-800 bg-slate-900 shadow-lg ${className}`}>
    {children}
  </div>
);
