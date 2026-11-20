import type { ReactElement } from 'react';
import { CheckIcon, DashIcon, ErrorIcon, WarnIcon, WorkingIcon } from './Icons';

export type StatusTone = 'ok' | 'warning' | 'error' | 'working' | 'muted';

const ICONS: Record<StatusTone, (p: { size?: number }) => ReactElement> = {
  ok: CheckIcon,
  warning: WarnIcon,
  error: ErrorIcon,
  working: WorkingIcon,
  muted: DashIcon,
};

const CLASS: Record<StatusTone, string> = {
  ok: 'status status-ok',
  warning: 'status status-warning',
  error: 'status status-error',
  working: 'status status-muted',
  muted: 'status status-muted',
};

/** Status is always an icon plus a word, never colour alone (spec 11). */
export function StatusChip({ tone, label }: { tone: StatusTone; label: string }): ReactElement {
  const Icon = ICONS[tone];
  return (
    <span className={CLASS[tone]}>
      <Icon size={14} />
      <span>{label}</span>
    </span>
  );
}
