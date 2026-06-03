export const Button = ({ children, variant, size, className, ...props }) => (
  <button className={`px-4 py-2 rounded font-medium transition-all active:scale-95 disabled:opacity-50 ${className}`} {...props}>
    {children}
  </button>
);
