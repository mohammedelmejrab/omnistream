import { useEffect, useRef, type RefObject } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function focusableIn(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => !el.closest('[hidden]'));
}

/**
 * Modal focus management: moves focus into the container on open, keeps Tab
 * inside it, and returns focus to the element that opened it on close
 * (spec 8: "focus returns to the trigger afterward").
 */
export function useModalFocus(
  open: boolean,
  containerRef: RefObject<HTMLElement | null>,
  initialRef?: RefObject<HTMLElement | null>,
): void {
  const opener = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!open || !container) return;
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const initial = initialRef?.current ?? focusableIn(container)[0] ?? container;
    initial.focus();
    return () => {
      const target = opener.current;
      opener.current = null;
      if (target && target.isConnected) {
        target.focus();
      } else {
        document.querySelector<HTMLElement>('#main h1')?.focus();
      }
    };
    // Only re-run when the dialog opens or closes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    const container = containerRef.current;
    if (!open || !container) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Tab') return;
      const items = focusableIn(container);
      if (items.length === 0) {
        e.preventDefault();
        container.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === container)) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first?.focus();
      }
    };
    container.addEventListener('keydown', onKey);
    return () => container.removeEventListener('keydown', onKey);
  }, [open, containerRef]);
}
