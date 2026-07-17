import { cn } from "@/lib/utils";

/**
 * BotForge mark — an abstract anvil + rising spark, drawn with the ember gradient.
 * The spark is the one warm note against the cool graphite UI.
 */
export function LogoMark({ className, size = 28 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={cn("shrink-0", className)}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="bf-ember" x1="4" y1="28" x2="28" y2="4" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FF6A3D" />
          <stop offset="1" stopColor="#FFB020" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="8" fill="#131519" stroke="#242832" />
      {/* anvil body */}
      <path
        d="M9 19.5h14l-2.4 3.2a2 2 0 0 1-1.6.8h-6a2 2 0 0 1-1.6-.8L9 19.5Z"
        fill="url(#bf-ember)"
        opacity="0.9"
      />
      <rect x="9" y="16.5" width="14" height="2.4" rx="1.2" fill="url(#bf-ember)" />
      {/* rising spark */}
      <path
        d="M16 6.5l1.7 4.1 4.1 1.7-4.1 1.7L16 18l-1.7-4L10.2 12.3l4.1-1.7L16 6.5Z"
        fill="url(#bf-ember)"
      />
    </svg>
  );
}

export function Logo({ className, collapsed }: { className?: string; collapsed?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      {!collapsed && (
        <span className="font-display text-[17px] font-semibold tracking-tight text-text">
          Bot<span className="text-ember-gradient">Forge</span>
        </span>
      )}
    </div>
  );
}
