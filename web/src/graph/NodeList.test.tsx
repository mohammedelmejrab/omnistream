import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { NodeList, type NodeListItem } from './NodeList';

const ITEMS: NodeListItem[] = [
  { id: 'a', label: 'Your question', meta: 'Your question' },
  { id: 'b', label: 'Energy', meta: 'Bubble' },
  { id: 'c', label: 'Searched Energy', meta: 'Step, Done' },
  { id: 'd', label: 'Answer', meta: 'Step, Done' },
];

function Harness({ onOpen }: { onOpen: (id: string) => void }) {
  const [activeId, setActiveId] = useState<string | null>(null);
  return (
    <NodeList
      label="Graph nodes"
      items={ITEMS}
      activeId={activeId}
      onActiveChange={setActiveId}
      onOpen={onOpen}
    />
  );
}

describe('NodeList keyboard path', () => {
  it('exposes a listbox with one tab stop (roving tabindex)', () => {
    render(<Harness onOpen={() => undefined} />);
    const options = within(screen.getByRole('listbox', { name: 'Graph nodes' })).getAllByRole('option');
    expect(options).toHaveLength(4);
    const stops = options.filter((o) => o.getAttribute('tabindex') === '0');
    expect(stops).toHaveLength(1);
  });

  it('Down and Up move focus, clamped at the ends', async () => {
    const user = userEvent.setup();
    render(<Harness onOpen={() => undefined} />);
    const options = screen.getAllByRole('option');
    options[0]!.focus();
    await user.keyboard('{ArrowUp}');
    expect(options[0]).toHaveFocus();
    await user.keyboard('{ArrowDown}{ArrowDown}');
    expect(options[2]).toHaveFocus();
    await user.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}');
    expect(options[3]).toHaveFocus();
  });

  it('Home and End jump to the first and last item', async () => {
    const user = userEvent.setup();
    render(<Harness onOpen={() => undefined} />);
    const options = screen.getAllByRole('option');
    options[1]!.focus();
    await user.keyboard('{End}');
    expect(options[3]).toHaveFocus();
    await user.keyboard('{Home}');
    expect(options[0]).toHaveFocus();
  });

  it('Enter opens the item; the focused item becomes selected', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(<Harness onOpen={onOpen} />);
    const options = screen.getAllByRole('option');
    options[2]!.focus();
    await user.keyboard('{Enter}');
    expect(onOpen).toHaveBeenCalledWith('c');
    expect(options[2]).toHaveAttribute('aria-selected', 'true');
  });

  it('a click opens the item too', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(<Harness onOpen={onOpen} />);
    await user.click(screen.getByText('Answer'));
    expect(onOpen).toHaveBeenCalledWith('d');
  });

  it('shows an empty status when there is nothing to list', () => {
    render(
      <NodeList label="Graph nodes" items={[]} activeId={null} onActiveChange={() => undefined} onOpen={() => undefined} />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('No items yet.');
  });
});
