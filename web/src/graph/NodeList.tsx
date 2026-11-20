import { useEffect, useRef } from 'react';

// The keyboard path to the graph (spec 10.3). Same data as the canvas.
// Roving tabindex: one tab stop, Up/Down/Home/End move, Enter opens the detail panel.

export interface NodeListItem {
  id: string;
  label: string;
  /** Plain-words description, for example "Bubble" or "Step done". */
  meta: string;
}

export interface NodeListProps {
  label: string;
  items: NodeListItem[];
  activeId: string | null;
  onActiveChange(id: string): void;
  onOpen(id: string): void;
}

export function NodeList({ label, items, activeId, onActiveChange, onOpen }: NodeListProps) {
  const refs = useRef<Map<string, HTMLLIElement>>(new Map());
  const activeIndex = Math.max(
    0,
    items.findIndex((i) => i.id === activeId),
  );

  // Keep focus where the user left it when the item list changes (live runs add nodes).
  useEffect(() => {
    if (items.length === 0) return;
    const first = items[0];
    if (!activeId && first) onActiveChange(first.id);
  }, [items, activeId, onActiveChange]);

  const focusAt = (index: number) => {
    const item = items[Math.min(items.length - 1, Math.max(0, index))];
    if (!item) return;
    onActiveChange(item.id);
    refs.current.get(item.id)?.focus();
  };

  if (items.length === 0) {
    return (
      <p className="node-list-empty" role="status">
        No items yet.
      </p>
    );
  }

  return (
    <ul role="listbox" aria-label={label} className="node-list" aria-orientation="vertical">
      {items.map((item, i) => {
        const selected = item.id === activeId;
        return (
          <li
            key={item.id}
            role="option"
            aria-selected={selected}
            tabIndex={i === activeIndex ? 0 : -1}
            className="node-list-item"
            ref={(el) => {
              if (el) refs.current.set(item.id, el);
              else refs.current.delete(item.id);
            }}
            onFocus={() => onActiveChange(item.id)}
            onKeyDown={(e) => {
              switch (e.key) {
                case 'ArrowDown':
                  e.preventDefault();
                  focusAt(i + 1);
                  break;
                case 'ArrowUp':
                  e.preventDefault();
                  focusAt(i - 1);
                  break;
                case 'Home':
                  e.preventDefault();
                  focusAt(0);
                  break;
                case 'End':
                  e.preventDefault();
                  focusAt(items.length - 1);
                  break;
                case 'Enter':
                case ' ':
                  e.preventDefault();
                  onOpen(item.id);
                  break;
              }
            }}
            onClick={() => onOpen(item.id)}
          >
            <span className="node-list-label">{item.label}</span>
            <span className="node-list-meta">{item.meta}</span>
          </li>
        );
      })}
    </ul>
  );
}
