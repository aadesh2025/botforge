// The exact launcher SVGs the widget renders (packages/widget/src/widget.js: ICON_CHAT,
// ICON_MESSAGE, ICON_DOTS). Kept here so the builder's design picker previews the real button,
// not a Lucide approximation. If you change one, change it in both places.

export function WidgetChatIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

/** Filled speech bubble with cut-through "text" lines. `cut` should be the button's background. */
export function WidgetMessageIcon({ className, cut = "currentColor" }: { className?: string; cut?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M20 2H4a2 2 0 0 0-2 2v18l4-4h14a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2z" />
      <rect x="6" y="8" width="12" height="1.8" rx="0.9" fill={cut} />
      <rect x="6" y="11.4" width="8" height="1.8" rx="0.9" fill={cut} />
    </svg>
  );
}

export function WidgetDotsIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <circle cx="8" cy="10" r="1" fill="currentColor" stroke="none" />
      <circle cx="12" cy="10" r="1" fill="currentColor" stroke="none" />
      <circle cx="16" cy="10" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}
