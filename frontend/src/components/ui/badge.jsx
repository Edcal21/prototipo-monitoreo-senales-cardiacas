export const Badge = ({ children, className }) => (
  <span className={`px-2 py-1 rounded-full text-xs font-bold text-white ${className}`}>
    {children}
  </span>
);
