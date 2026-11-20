import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import type { Bubble, Source } from '@/api/types';
import { Composer, type BlockReason } from './Composer';
import type { Mention } from './mentions';

const bubble: Bubble = {
  id: 'b1',
  name: 'Energy',
  description: '',
  half_life_days: 30,
  created_at: '2026-11-18T09:00:00Z',
  updated_at: '2026-11-18T09:00:00Z',
};
const feed: Source = {
  id: 's1',
  type: 'rss',
  url: 'https://example.com/feed',
  credibility: 0.5,
  poll_interval: 900,
  bubble_ids: ['b1'],
  api_mapping: null,
  max_items_per_hour: 30,
  store_full_text: true,
  enabled: true,
  last_polled_at: null,
  status: 'ok',
  last_error: null,
};

interface HarnessProps {
  onSend?: () => void;
  blockedReason?: BlockReason | null;
  running?: boolean;
  initial?: string;
  onStop?: () => void;
}

function Harness(props: HarnessProps) {
  const [value, setValue] = useState(props.initial ?? '');
  const [mode, setMode] = useState<'normal' | 'agentic'>('normal');
  const [mentions, setMentions] = useState<Mention[]>([]);
  return (
    <MemoryRouter>
      <Composer
        value={value}
        onValueChange={setValue}
        mode={mode}
        onModeChange={setMode}
        bubbles={[bubble]}
        sources={[feed]}
        mentions={mentions}
        onMentionsChange={setMentions}
        blockedReason={props.blockedReason ?? null}
        running={props.running ?? false}
        onSend={props.onSend ?? (() => undefined)}
        onStop={props.onStop ?? (() => undefined)}
        onOpenSources={() => undefined}
      />
    </MemoryRouter>
  );
}

describe('Composer', () => {
  it('sends on Enter and inserts a newline on Shift+Enter', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);
    const box = screen.getByRole('combobox', { name: 'Your question' });
    await user.type(box, 'Line one');
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    expect(onSend).not.toHaveBeenCalled();
    await user.type(box, 'two');
    expect(box).toHaveValue('Line one\ntwo');
    await user.keyboard('{Enter}');
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it('keeps Send disabled while the question is empty', () => {
    render(<Harness />);
    expect(screen.getByRole('button', { name: 'Send question' })).toHaveAttribute('aria-disabled', 'true');
  });

  it('disables sending past the 20,000 character limit and says by how much', () => {
    render(<Harness initial={'x'.repeat(20_010)} />);
    expect(screen.getByRole('button', { name: 'Send question' })).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText(/Over the limit by 10 characters/)).toBeInTheDocument();
  });

  it('shows the counter near the limit', () => {
    render(<Harness initial={'x'.repeat(18_500)} />);
    expect(screen.getByText('18,500 / 20,000')).toBeInTheDocument();
  });

  it('shows why sending is blocked, with a link to fix it', () => {
    render(
      <Harness
        initial="hello"
        blockedReason={{ text: 'No provider key is set.', to: '/app/settings', linkLabel: 'Add a key in Settings' }}
      />,
    );
    expect(screen.getByText('No provider key is set.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Add a key in Settings' })).toHaveAttribute('href', '/app/settings');
    expect(screen.getByRole('button', { name: 'Send question' })).toHaveAttribute('aria-disabled', 'true');
  });

  it('swaps Send for a Stop button while a run is in progress and disables input', () => {
    const onStop = vi.fn();
    render(<Harness running onStop={onStop} />);
    expect(screen.getByRole('combobox', { name: 'Your question' })).toBeDisabled();
    screen.getByRole('button', { name: 'Stop run' }).click();
    expect(onStop).toHaveBeenCalled();
  });

  it('opens a bubble and source list with @ and adds the chosen bubble as a chip', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const box = screen.getByRole('combobox', { name: 'Your question' });
    await user.type(box, 'what about @ene');
    const listbox = screen.getByRole('listbox', { name: 'Bubbles and sources' });
    expect(listbox).toHaveTextContent('Energy');
    expect(box).toHaveAttribute('aria-expanded', 'true');
    await user.keyboard('{Enter}');
    expect(screen.getByText('Bubble: Energy')).toBeInTheDocument();
    expect(box).toHaveValue('what about ');
  });
});
