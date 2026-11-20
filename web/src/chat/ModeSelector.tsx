import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactElement } from 'react';
import type { RunMode } from '@/api/types';
import { ChevronIcon } from '@/components/Icons';
import { MODES, MODE_ORDER } from './modes';
import { ModeMarker } from './ModeMarker';

interface ModeSelectorProps {
  value: RunMode;
  onChange: (mode: RunMode) => void;
  disabled?: boolean;
}

/**
 * Menu button that opens a radio group (spec 6 and 7, decision 26). Each
 * option shows its description inside the open menu. The button's
 * aria-describedby names the current mode's description.
 */
export function ModeSelector({ value, onChange, disabled = false }: ModeSelectorProps): ReactElement {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const descId = useId();
  const current = MODES[value];

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent): void => {
      const target = e.target as Node;
      if (menuRef.current?.contains(target) || buttonRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
  }, [open]);

  function close(returnFocus: boolean): void {
    setOpen(false);
    if (returnFocus) buttonRef.current?.focus();
  }

  function choose(mode: RunMode): void {
    onChange(mode);
    close(true);
  }

  function onMenuKey(e: KeyboardEvent<HTMLDivElement>): void {
    if (e.key === 'Escape') {
      e.preventDefault();
      close(true);
      return;
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      const idx = MODE_ORDER.indexOf(value);
      const step = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : -1;
      const next = MODE_ORDER[(idx + step + MODE_ORDER.length) % MODE_ORDER.length];
      if (next) {
        onChange(next);
        menuRef.current?.querySelector<HTMLElement>(`[data-mode="${next}"]`)?.focus();
      }
    }
  }

  return (
    <div className="mode-selector">
      <button
        ref={buttonRef}
        type="button"
        className="mode-button btn-pill"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-describedby={descId}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        <ModeMarker mode={value} />
        <span>{current.label}</span>
        <ChevronIcon size={14} />
      </button>
      <span id={descId} className="sr-only">
        {current.label} mode: {current.description}
      </span>
      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="radiogroup"
          aria-label="Answer mode"
          className="mode-menu"
          onKeyDown={onMenuKey}
        >
          {MODE_ORDER.map((m) => {
            const info = MODES[m];
            const checked = m === value;
            return (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={checked}
                data-mode={m}
                tabIndex={checked ? 0 : -1}
                aria-describedby={`${descId}-${m}`}
                className={checked ? 'mode-option mode-option-checked' : 'mode-option'}
                onClick={() => choose(m)}
              >
                <span className="mode-option-head">
                  <ModeMarker mode={m} />
                  <span className="mode-option-label">{info.label}</span>
                </span>
                <span id={`${descId}-${m}`} className="mode-option-desc">
                  {info.description}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
