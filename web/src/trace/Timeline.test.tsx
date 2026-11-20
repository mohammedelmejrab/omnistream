import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Timeline, type TimelineItem } from './Timeline';

const items: TimelineItem[] = [
  { id: 'a', label: 'Understood your question', durationMs: 1, statusWord: 'Done', statusClass: 'stage-done' },
  { id: 'b', label: 'Gathered evidence', durationMs: 18, statusWord: 'Done', statusClass: 'stage-done' },
];

describe('Timeline', () => {
  it('gives each bar a visible tooltip label with its step number and duration', () => {
    const { container } = render(
      <Timeline label="Duration of each stage" items={items} currentIndex={-1} onSelect={vi.fn()} variant="stages" />,
    );
    const bars = container.querySelectorAll<HTMLButtonElement>('.timeline-bar');
    expect(bars[0]?.dataset['label']).toBe('1 Understood your question: 1 ms');
    expect(bars[1]?.dataset['label']).toBe('2 Gathered evidence: 18 ms');
  });

  it('anchors each tooltip to the nearer half of the strip so it stays inside the strip', () => {
    const many: TimelineItem[] = Array.from({ length: 6 }, (_, i) => ({
      id: `s${i}`,
      label: `Step ${i}`,
      durationMs: 10,
      statusWord: 'Done',
      statusClass: 'stage-done',
    }));
    const { container } = render(
      <Timeline label="Timeline of steps" items={many} currentIndex={-1} onSelect={vi.fn()} />,
    );
    const edges = Array.from(container.querySelectorAll<HTMLButtonElement>('.timeline-bar'), (b) => b.dataset['edge']);
    expect(edges).toEqual(['start', 'start', 'start', 'end', 'end', 'end']);
  });

  it('keeps the accessible name with the status word', () => {
    render(<Timeline label="Duration of each stage" items={items} currentIndex={1} onSelect={vi.fn()} variant="stages" />);
    const bar = screen.getByRole('button', { name: 'Gathered evidence, Done, 18 ms' });
    expect(bar).toHaveAttribute('aria-current', 'step');
  });

  it('sizes bars by duration alone, so a zero-length step gets only the 4px minimum', () => {
    const { container } = render(
      <Timeline
        label="Duration of each stage"
        items={[{ ...items[0]!, durationMs: 0 }, items[1]!]}
        currentIndex={-1}
        onSelect={vi.fn()}
      />,
    );
    const bars = container.querySelectorAll<HTMLButtonElement>('.timeline-bar');
    expect(bars[0]?.style.flexGrow).toBe('0');
    expect(bars[1]?.style.flexGrow).toBe('18');
  });

  it('calls onSelect with the bar index', async () => {
    const onSelect = vi.fn();
    render(<Timeline label="Duration of each stage" items={items} currentIndex={-1} onSelect={onSelect} />);
    screen.getByRole('button', { name: /Gathered evidence/ }).click();
    expect(onSelect).toHaveBeenCalledWith(1);
  });
});
