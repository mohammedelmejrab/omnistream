import type { ReactElement } from 'react';
import type { RunMode } from '@/api/types';

/** Blue circle for Normal, Mauve diamond for Agentic (spec 7). Decorative. */
export function ModeMarker({ mode, size = 10 }: { mode: RunMode; size?: number }): ReactElement {
  if (mode === 'agentic') {
    return (
      <svg width={size} height={size} viewBox="0 0 10 10" aria-hidden="true" focusable="false" className="mode-marker mode-agentic">
        <path d="M5 0 10 5 5 10 0 5z" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 10 10" aria-hidden="true" focusable="false" className="mode-marker mode-normal">
      <circle cx="5" cy="5" r="5" fill="currentColor" />
    </svg>
  );
}

/** Shape, colour and word together. */
export function ModeBadge({ mode }: { mode: RunMode }): ReactElement {
  const label = mode === 'agentic' ? 'Agentic' : 'Normal';
  return (
    <span className={`mode-badge mode-${mode}`}>
      <ModeMarker mode={mode} size={9} />
      <span>{label}</span>
    </span>
  );
}
