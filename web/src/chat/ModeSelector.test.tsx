import { useState } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { RunMode } from '@/api/types';
import { ModeSelector } from './ModeSelector';

function Harness({ onChange }: { onChange: (m: RunMode) => void }) {
  const [mode, setMode] = useState<RunMode>('normal');
  return (
    <ModeSelector
      value={mode}
      onChange={(m) => {
        setMode(m);
        onChange(m);
      }}
    />
  );
}

describe('ModeSelector', () => {
  it('names the current mode description on the menu button', () => {
    render(<ModeSelector value="agentic" onChange={() => undefined} />);
    const button = screen.getByRole('button', { name: /agentic/i });
    const described = document.getElementById(button.getAttribute('aria-describedby') ?? '');
    expect(described).toHaveTextContent(/Agentic mode: Multi-domain/);
  });

  it('opens a radio group whose options show their descriptions', async () => {
    const user = userEvent.setup();
    render(<Harness onChange={() => undefined} />);
    await user.click(screen.getByRole('button', { name: /normal/i }));
    const group = screen.getByRole('radiogroup', { name: 'Answer mode' });
    const radios = within(group).getAllByRole('radio');
    expect(radios).toHaveLength(2);
    expect(radios[0]).toHaveAttribute('aria-checked', 'true');
    expect(radios[1]).toHaveTextContent('Multi-domain or open-ended');
  });

  it('moves between modes with arrow keys and closes on Escape, returning focus', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const button = screen.getByRole('button', { name: /normal/i });
    await user.click(button);
    await user.keyboard('{ArrowDown}');
    expect(onChange).toHaveBeenLastCalledWith('agentic');
    expect(screen.getByRole('radio', { name: /agentic/i })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it('chooses an option with Enter and reflects the choice on the button', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await user.click(screen.getByRole('button', { name: /normal/i }));
    await user.click(screen.getByRole('radio', { name: /agentic/i }));
    expect(onChange).toHaveBeenCalledWith('agentic');
    expect(screen.getByRole('button', { name: /agentic/i })).toBeInTheDocument();
  });
});
