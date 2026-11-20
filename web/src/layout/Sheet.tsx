import { useRef, type ReactElement, type ReactNode } from 'react';
import { useModalFocus } from '@/hooks/useModalFocus';

interface SheetProps {
  open: boolean;
  onClose: () => void;
  titleId: string;
  title: string;
  children: ReactNode;
}

/**
 * Side sheet (spec 8). Square corners on the viewport edge, 20px rounding on
 * the inner edge. Full screen below 768px (spec 11.1, decision 31).
 */
export function Sheet({ open, onClose, titleId, title, children }: SheetProps): ReactElement | null {
  const panelRef = useRef<HTMLElement>(null);
  useModalFocus(open, panelRef);
  if (!open) return null;
  return (
    <div className="scrim scrim-side" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <section
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="sheet"
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.stopPropagation();
            onClose();
          }
        }}
      >
        <div className="sheet-header">
          <h2 id={titleId} className="sheet-title">
            {title}
          </h2>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="sheet-body">{children}</div>
      </section>
    </div>
  );
}
