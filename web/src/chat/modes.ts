import type { RunMode } from '@/api/types';

export interface ModeInfo {
  mode: RunMode;
  label: string;
  description: string;
  /** Shape is the second cue; colour is never the only cue (spec 7). */
  shape: 'circle' | 'diamond';
}

export const MODES: Record<RunMode, ModeInfo> = {
  normal: {
    mode: 'normal',
    label: 'Normal',
    description: 'Fast, predictable answers. One pass over the selected bubbles.',
    shape: 'circle',
  },
  agentic: {
    mode: 'agentic',
    label: 'Agentic',
    description:
      'Multi-domain or open-ended questions. An orchestrator routes to each bubble, then merges their findings.',
    shape: 'diamond',
  },
};

export const MODE_ORDER: readonly RunMode[] = ['normal', 'agentic'];

export const DEFAULT_MODE: RunMode = 'normal';

export function isRunMode(value: unknown): value is RunMode {
  return value === 'normal' || value === 'agentic';
}
