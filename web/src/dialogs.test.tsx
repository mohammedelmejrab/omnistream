import { useRef, useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Sheet } from '@/layout/Sheet';

function ConfirmHarness({ onConfirm }: { onConfirm: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Delete thing
      </button>
      <ConfirmDialog
        open={open}
        title="Delete this?"
        description="It will be gone."
        confirmLabel="Delete"
        danger
        onConfirm={() => {
          onConfirm();
          setOpen(false);
        }}
        onCancel={() => setOpen(false)}
      />
    </>
  );
}

describe('ConfirmDialog', () => {
  it('is an alertdialog that starts on Cancel and returns focus to its trigger', async () => {
    const user = userEvent.setup();
    render(<ConfirmHarness onConfirm={() => undefined} />);
    const trigger = screen.getByRole('button', { name: 'Delete thing' });
    await user.click(trigger);
    expect(screen.getByRole('alertdialog', { name: 'Delete this?' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('confirms the action', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<ConfirmHarness onConfirm={onConfirm} />);
    await user.click(screen.getByRole('button', { name: 'Delete thing' }));
    await user.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

function SheetHarness() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={ref} type="button" onClick={() => setOpen(true)}>
        Open sheet
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} titleId="t" title="Sources">
        <button type="button">Inside</button>
      </Sheet>
    </>
  );
}

describe('Sheet', () => {
  it('traps Tab inside the dialog and closes with Escape', async () => {
    const user = userEvent.setup();
    render(<SheetHarness />);
    await user.click(screen.getByRole('button', { name: 'Open sheet' }));
    const dialog = screen.getByRole('dialog', { name: 'Sources' });
    expect(dialog).toBeInTheDocument();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Inside' })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Inside' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open sheet' })).toHaveFocus();
  });
});
