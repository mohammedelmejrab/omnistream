import type { ReactElement } from 'react';
import { StarCanvas } from './StarCanvas';

/**
 * Home-screen starfield (spec 11.3). Off when the Settings toggle is off. It always animates,
 * whatever the device's motion setting; the toggle is the way to switch it off.
 */
export function StarBackground({ enabled, paused }: { enabled: boolean; paused?: boolean }): ReactElement | null {
  if (!enabled) return null;
  return (
    <div className="star-background" aria-hidden="true" data-testid="star-background">
      <StarCanvas mode="animated" {...(paused !== undefined ? { paused } : {})} />
    </div>
  );
}
