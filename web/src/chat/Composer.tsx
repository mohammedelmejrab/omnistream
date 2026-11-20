import {
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
  type RefObject,
} from 'react';
import { Link } from 'react-router';
import type { Bubble, RunMode, Source } from '@/api/types';
import { ArrowUpIcon, PlusIcon, StopIcon } from '@/components/Icons';
import {
  buildOptions,
  COUNTER_THRESHOLD,
  filterOptions,
  findMentionQuery,
  MAX_QUESTION_CHARS,
  resolveScope,
  type Mention,
  type MentionOption,
  type MentionQuery,
} from './mentions';
import { ModeSelector } from './ModeSelector';

export const PLACEHOLDER = 'Ask OmniStream, or type @ for bubbles and sources';

const LINE_HEIGHT = 24;
const TEXT_PADDING_Y = 12;
const MAX_LINES = 6;
const WRAP_THRESHOLD = LINE_HEIGHT + TEXT_PADDING_Y * 2 + 4;

/** Why sending is blocked, with an optional link to fix it. */
export interface BlockReason {
  text: string;
  to?: string;
  linkLabel?: string;
}

export interface ComposerProps {
  value: string;
  onValueChange: (value: string) => void;
  mode: RunMode;
  onModeChange: (mode: RunMode) => void;
  bubbles: readonly Bubble[];
  sources: readonly Source[];
  mentions: readonly Mention[];
  onMentionsChange: (mentions: Mention[]) => void;
  /** Why sending is blocked for reasons outside the input (no key, no bubbles, offline). */
  blockedReason: BlockReason | null;
  running: boolean;
  onSend: () => void;
  onStop: () => void;
  onOpenSources: () => void;
  /** Extra text shown under the bar (e.g. a retry hint). */
  footer?: ReactNode;
  inputRef?: RefObject<HTMLTextAreaElement | null>;
  autoFocus?: boolean;
}

/**
 * The single input bar (spec 6). Enter sends, Shift+Enter inserts a newline,
 * "@" opens the mention combobox (ARIA combobox pattern).
 */
export function Composer(props: ComposerProps): ReactElement {
  const {
    value,
    onValueChange,
    mode,
    onModeChange,
    bubbles,
    sources,
    mentions,
    onMentionsChange,
    blockedReason,
    running,
    onSend,
    onStop,
    onOpenSources,
    footer,
    inputRef,
    autoFocus,
  } = props;

  const localRef = useRef<HTMLTextAreaElement>(null);
  const textareaRef = inputRef ?? localRef;
  const [wrapped, setWrapped] = useState(false);
  const [mention, setMention] = useState<MentionQuery | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const pendingCaret = useRef<number | null>(null);
  const listId = useId();
  const counterId = useId();
  const options = useMemo(() => buildOptions(bubbles, sources), [bubbles, sources]);
  const matches: MentionOption[] = mention ? filterOptions(options, mention.query) : [];
  const listOpen = mention !== null && matches.length > 0;
  const active = matches[Math.min(activeIndex, matches.length - 1)];

  const scope = resolveScope(mentions, bubbles, sources);
  const missingIds = new Set(scope.missing.map((m) => m.id));
  const length = value.length;
  const overBy = length - MAX_QUESTION_CHARS;
  const overLimit = overBy > 0;
  const showCounter = length >= COUNTER_THRESHOLD;
  const scopeBlocked = mentions.length > 0 && scope.blocked;
  const trimmedEmpty = value.trim().length === 0;
  const sendBlockedBy: BlockReason | null = running
    ? null
    : overLimit
      ? { text: `Over the limit by ${overBy.toLocaleString()} characters.` }
      : scopeBlocked
        ? { text: 'The selected bubbles no longer exist. Remove them to continue.' }
        : blockedReason;
  const canSend = !running && !trimmedEmpty && !overLimit && !scopeBlocked && !blockedReason;

  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const maxHeight = LINE_HEIGHT * MAX_LINES + TEXT_PADDING_Y * 2;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    setWrapped(el.scrollHeight > WRAP_THRESHOLD);
  }, [value, textareaRef]);

  useLayoutEffect(() => {
    if (pendingCaret.current === null) return;
    const el = textareaRef.current;
    if (el) {
      el.setSelectionRange(pendingCaret.current, pendingCaret.current);
    }
    pendingCaret.current = null;
  }, [value, textareaRef]);

  function handleChange(e: ChangeEvent<HTMLTextAreaElement>): void {
    const next = e.target.value;
    onValueChange(next);
    const found = findMentionQuery(next, e.target.selectionStart ?? next.length);
    setMention(found);
    setActiveIndex(0);
  }

  function selectOption(option: MentionOption): void {
    if (!mention) return;
    const el = textareaRef.current;
    const caret = el?.selectionStart ?? value.length;
    const before = value.slice(0, mention.start);
    const after = value.slice(caret);
    onValueChange(before + after);
    pendingCaret.current = before.length;
    if (!mentions.some((m) => m.kind === option.kind && m.id === option.id)) {
      onMentionsChange([...mentions, { kind: option.kind, id: option.id, label: option.label }]);
    }
    setMention(null);
    setActiveIndex(0);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>): void {
    if (listOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % matches.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => (i - 1 + matches.length) % matches.length);
        return;
      }
      if ((e.key === 'Enter' || e.key === 'Tab') && active) {
        e.preventDefault();
        selectOption(active);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        setMention(null);
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (running) return;
      if (canSend) onSend();
    }
  }

  function removeMention(m: Mention): void {
    onMentionsChange(mentions.filter((x) => !(x.kind === m.kind && x.id === m.id)));
  }

  const describedBy = [counterId].join(' ');

  return (
    <div className="composer-wrap">
      <form
        className="composer"
        data-wrapped={wrapped ? 'true' : 'false'}
        aria-label="Ask a question"
        onSubmit={(e) => {
          e.preventDefault();
          if (running) return;
          if (canSend) onSend();
        }}
      >
        {mentions.length > 0 && (
          <ul className="mention-chips" aria-label="Selected bubbles and sources">
            {mentions.map((m) => {
              const gone = missingIds.has(m.id);
              return (
                <li key={`${m.kind}-${m.id}`} className={gone ? 'mention-chip mention-gone' : 'mention-chip'}>
                  <span>
                    {m.kind === 'bubble' ? 'Bubble' : 'Source'}: {m.label}
                    {gone ? ' (no longer exists)' : ''}
                  </span>
                  <button type="button" className="chip-remove" onClick={() => removeMention(m)} aria-label={`Remove ${m.label}`}>
                    ×
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <div className="composer-row">
          <button
            type="button"
            className="icon-btn"
            aria-label="Open sources menu"
            onClick={onOpenSources}
          >
            <PlusIcon size={18} />
          </button>
          <textarea
            ref={textareaRef}
            className="composer-input"
            rows={1}
            role="combobox"
            aria-label="Your question"
            aria-expanded={listOpen}
            aria-controls={listOpen ? listId : undefined}
            aria-autocomplete="list"
            aria-activedescendant={listOpen && active ? `${listId}-${activeIndex}` : undefined}
            aria-describedby={describedBy}
            aria-invalid={overLimit ? true : undefined}
            placeholder={PLACEHOLDER}
            value={value}
            disabled={running}
            autoFocus={autoFocus}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onBlur={() => setMention(null)}
          />
          <div className="composer-end">
            <ModeSelector value={mode} onChange={onModeChange} disabled={running} />
            {running ? (
              <button type="button" className="send-btn send-stop" aria-label="Stop run" onClick={onStop}>
                <StopIcon size={18} />
                <span className="sr-only">Stop</span>
              </button>
            ) : (
              <button
                type="button"
                className="send-btn"
                aria-label="Send question"
                aria-disabled={!canSend}
                disabled={!canSend}
                onClick={() => canSend && onSend()}
              >
                <ArrowUpIcon size={20} />
              </button>
            )}
          </div>
        </div>
        {listOpen && (
          <ul id={listId} role="listbox" aria-label="Bubbles and sources" className="mention-list">
            {matches.map((o, i) => (
              <li
                key={`${o.kind}-${o.id}`}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === activeIndex}
                className={i === activeIndex ? 'mention-option mention-option-active' : 'mention-option'}
                onMouseDown={(e) => {
                  e.preventDefault();
                  selectOption(o);
                }}
                onMouseEnter={() => setActiveIndex(i)}
              >
                <span className="mention-option-label">{o.label}</span>
                <span className="mention-option-detail">{o.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </form>
      <div className="composer-meta" id={counterId}>
        {showCounter && (
          <span className={overLimit ? 'counter counter-over' : 'counter'} aria-live="polite">
            {length.toLocaleString()} / {MAX_QUESTION_CHARS.toLocaleString()}
          </span>
        )}
        {sendBlockedBy && (
          <span className="send-reason" role="status">
            {sendBlockedBy.text}
            {sendBlockedBy.to && sendBlockedBy.linkLabel ? (
              <>
                {' '}
                <Link to={sendBlockedBy.to}>{sendBlockedBy.linkLabel}</Link>
              </>
            ) : null}
          </span>
        )}
        {footer}
      </div>
    </div>
  );
}
