// Timeline strip: one bar per item, width proportional to duration, 4px minimum (spec 10.3).
// Bars are buttons, so the strip can be used from the keyboard and seeks the replay.
// Each bar carries a tooltip (data-label, shown on hover and focus) with its number, name and duration.
import { formatDuration } from './format';

export interface TimelineItem {
  id: string;
  label: string;
  durationMs: number | null;
  /** Status word for the accessible name, for example "Done". */
  statusWord: string;
  /** Status class for colour, never the only cue (the word is in the name). */
  statusClass: string;
}

export interface TimelineProps {
  label: string;
  items: TimelineItem[];
  /** Index of the item the replay is on, or -1. */
  currentIndex: number;
  onSelect(index: number): void;
  variant?: 'steps' | 'stages';
}

export function Timeline({ label, items, currentIndex, onSelect, variant = 'steps' }: TimelineProps) {
  if (items.length === 0) return null;
  return (
    <div className={`timeline timeline-${variant}`} role="group" aria-label={label}>
      {items.map((item, i) => {
        const dur = item.durationMs ?? 0;
        const durText = item.durationMs === null ? 'duration unknown' : `${item.durationMs} ms`;
        const tipTime = item.durationMs === null ? 'duration unknown' : formatDuration(item.durationMs);
        return (
          <button
            key={item.id}
            type="button"
            className={`timeline-bar ${item.statusClass}`}
            style={{ flexGrow: dur }}
            aria-label={`${item.label}, ${item.statusWord}, ${durText}`}
            data-label={`${i + 1} ${item.label}: ${tipTime}`}
            data-edge={i < items.length / 2 ? 'start' : 'end'}
            aria-current={i === currentIndex ? 'step' : undefined}
            onClick={() => onSelect(i)}
          />
        );
      })}
    </div>
  );
}
