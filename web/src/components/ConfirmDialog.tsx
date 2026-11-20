import { useRef, type ReactElement } from 'react';
import { useModalFocus } from '@/hooks/useModalFocus';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Confirmation in an alertdialog (spec 8, 10.6). Cancel gets initial focus. */
export function ConfirmDialog(props: ConfirmDialogProps): ReactElement | null {
  const { open, title, description, confirmLabel, danger, busy, onConfirm, onCancel } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = 'confirm-title';
  const descId = 'confirm-desc';
  useModalFocus(open, containerRef, cancelRef);

  if (!open) return null;
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onCancel()}>
      <div
        ref={containerRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        tabIndex={-1}
        className="dialog"
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.stopPropagation();
            onCancel();
          }
        }}
      >
        <h2 id={titleId} className="dialog-title">
          {title}
        </h2>
        <p id={descId} className="muted">
          {description}
        </p>
        <div className="dialog-actions">
          <button ref={cancelRef} type="button" className="btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className={danger ? 'btn btn-danger' : 'btn btn-primary'}
            onClick={onConfirm}
            disabled={busy}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
