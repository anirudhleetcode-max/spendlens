export function Logo({ size = 26, light = false }: { size?: number; light?: boolean }) {
  const bg = light ? "#f6f1e7" : "#1f4d3a";
  const fg = light ? "#1f4d3a" : "#f6f1e7";
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="5" fill={bg} />
      <path d="M10 7h12v18l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5-2 1.5z" fill={fg} />
      <path d="M13 12h6M13 16h6M13 20h4" stroke={bg} strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
