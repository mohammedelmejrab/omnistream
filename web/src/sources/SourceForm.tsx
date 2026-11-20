import { useId, useRef, useState, type FormEvent, type ReactElement } from 'react';
import { createSource, listSources, patchSource, testSource, type SourceCreateInput, type TestedItem } from '@/api/sources';
import { ApiError, NetworkError, isNotFound } from '@/api/client';
import type { ApiMapping, Bubble, Source } from '@/api/types';
import { Notice } from '@/components/Notice';
import { POLL_OPTIONS } from './sourceStatus';
import { findDuplicateSource, isValidHttpUrl, parseCredibility, parsePositiveInt } from './validation';

interface SourceFormProps {
  kind: 'rss' | 'api';
  /** Present when editing. Only the fields the server can patch are editable. */
  source?: Source;
  bubbles: readonly Bubble[];
  existing: readonly Source[];
  onSaved: (source: Source, note: string) => void;
  onCancel: () => void;
}

interface HeaderRow {
  name: string;
  value: string;
}

type Errors = Partial<Record<'url' | 'bubbles' | 'credibility' | 'backfill' | 'rate' | 'items' | 'body' | 'mapUrl' | 'headers' | 'save', string>>;

function messageOf(err: unknown): string {
  if (err instanceof NetworkError) return 'OmniStream server is unreachable. Your entry is kept.';
  if (err instanceof ApiError) return err.message;
  return 'Something went wrong. Your entry is kept.';
}

/**
 * Add or edit a feed or API source. Inline validation runs before submit
 * (spec 8). Editing keeps the user's values if the poll changes the source.
 */
export function SourceForm(props: SourceFormProps): ReactElement {
  const { kind, source, bubbles, existing, onSaved, onCancel } = props;
  const editing = source !== undefined;
  const id = useId();
  const editedAt = useRef(source?.last_polled_at ?? null);

  const [url, setUrl] = useState(source?.url ?? '');
  const [bubbleIds, setBubbleIds] = useState<string[]>(source?.bubble_ids ?? []);
  const [poll, setPoll] = useState(String(source?.poll_interval ?? 900));
  const [credibility, setCredibility] = useState(String(source?.credibility ?? 0.5));
  const [backfill, setBackfill] = useState('');
  const [fullText, setFullText] = useState(source?.store_full_text ?? true);
  const [enabled, setEnabled] = useState(source?.enabled ?? true);
  const [rate, setRate] = useState(String(source?.max_items_per_hour ?? 30));
  const mapping = source?.api_mapping ?? null;
  const [itemsPath, setItemsPath] = useState(mapping?.items ?? '');
  const [titlePath, setTitlePath] = useState(mapping?.title ?? '');
  const [bodyPath, setBodyPath] = useState(mapping?.body ?? '');
  const [datePath, setDatePath] = useState(mapping?.date ?? '');
  const [urlPath, setUrlPath] = useState(mapping?.url ?? '');
  const [headers, setHeaders] = useState<HeaderRow[]>([{ name: '', value: '' }]);

  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState<'save' | 'test' | null>(null);
  const [testResult, setTestResult] = useState<{ items: TestedItem[] } | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<Source | null>(null);

  function toggleBubble(bubbleId: string, checked: boolean): void {
    setBubbleIds((prev) => (checked ? [...prev, bubbleId] : prev.filter((b) => b !== bubbleId)));
  }

  /** Validates and builds the request body. Returns null and sets errors when invalid. */
  function build(): SourceCreateInput | null {
    const next: Errors = {};
    const cred = parseCredibility(credibility);
    const rateN = parsePositiveInt(rate);
    if (!editing && !isValidHttpUrl(url)) next.url = 'Enter a full address that starts with http:// or https://.';
    if (bubbleIds.length === 0) next.bubbles = 'Choose at least one bubble for this source.';
    if (cred === null) next.credibility = 'Credibility must be a number from 0 to 1.';
    if (kind === 'rss' && backfill.trim() !== '' && parsePositiveInt(backfill) === null) {
      next.backfill = 'Backfill must be a whole number of days, 1 or more.';
    }
    if (kind === 'api') {
      if (rateN === null) next.rate = 'Rate limit must be a whole number, 1 or more.';
      if (!itemsPath.trim()) next.items = 'Enter the path to the list of items.';
      if (!bodyPath.trim()) next.body = 'Enter the path to each item body.';
      if (!urlPath.trim()) next.mapUrl = 'Enter the path to each item link.';
      const named = headers.filter((h) => h.name.trim() || h.value.trim());
      if (named.some((h) => !h.name.trim())) next.headers = 'Every header needs a name.';
      if (Object.keys(next).length) {
        setErrors(next);
        return null;
      }
      const headerMap: Record<string, string> = {};
      if (!editing) for (const h of named) headerMap[h.name.trim()] = h.value;
      const apiMapping: ApiMapping = {
        items: itemsPath.trim(),
        title: titlePath.trim() || null,
        body: bodyPath.trim(),
        date: datePath.trim() || null,
        url: urlPath.trim(),
        headers: headerMap,
      };
      return {
        type: 'api',
        url: url.trim(),
        credibility: cred ?? 0.5,
        poll_interval: Number(poll),
        bubble_ids: bubbleIds,
        api_mapping: apiMapping,
        max_items_per_hour: rateN ?? 30,
        store_full_text: fullText,
        enabled,
      };
    }
    if (Object.keys(next).length) {
      setErrors(next);
      return null;
    }
    const days = parsePositiveInt(backfill);
    return {
      type: 'rss',
      url: url.trim(),
      credibility: cred ?? 0.5,
      poll_interval: Number(poll),
      bubble_ids: bubbleIds,
      max_items_per_hour: rateN ?? 30,
      store_full_text: fullText,
      enabled,
      ...(days !== null ? { backfill_days: days } : {}),
    };
  }

  /**
   * The source with this URL on the server, if any. Falls back to the list the
   * panel holds when the server list cannot be read.
   */
  async function findCurrentDuplicate(rawUrl: string): Promise<Source | undefined> {
    try {
      return findDuplicateSource(await listSources(), rawUrl);
    } catch {
      return findDuplicateSource(existing, rawUrl);
    }
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setDuplicate(null);
    setErrors({});
    const input = build();
    if (!input) return;
    setBusy('save');
    try {
      if (!editing) {
        // Check the server's list now, not the list the panel loaded earlier.
        const dup = await findCurrentDuplicate(url);
        if (dup) {
          setDuplicate(dup);
          return;
        }
      }
      if (source) {
        const patch = {
          enabled: input.enabled,
          credibility: input.credibility,
          poll_interval: input.poll_interval,
          bubble_ids: input.bubble_ids,
          max_items_per_hour: input.max_items_per_hour,
          store_full_text: input.store_full_text,
        };
        const updated = await patchSource(source.id, patch);
        const changedInBackground = (updated.last_polled_at ?? null) !== editedAt.current;
        onSaved(
          updated,
          changedInBackground
            ? 'Saved. The source was updated in the background while you were editing; your values are kept.'
            : 'Source saved.',
        );
      } else {
        const created = await createSource(input);
        onSaved(created, 'Source added. Ingestion runs in the background.');
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // The server refused a duplicate that the check above did not see.
        const dup = await findCurrentDuplicate(url);
        if (dup) {
          setDuplicate(dup);
          return;
        }
      }
      setErrors({ save: messageOf(err) });
    } finally {
      setBusy(null);
    }
  }

  async function onTest(): Promise<void> {
    setTestResult(null);
    setTestError(null);
    const input = build();
    if (!input) return;
    setBusy('test');
    try {
      const result = await testSource(input);
      setTestResult({ items: result.items.slice(0, 5) });
    } catch (err) {
      if (isNotFound(err) || (err instanceof ApiError && err.status === 405)) {
        setTestError('Testing a source is not available on this server yet.');
      } else {
        setTestError(messageOf(err));
      }
    } finally {
      setBusy(null);
    }
  }

  const title = editing ? 'Edit source' : kind === 'rss' ? 'Add a feed' : 'Add an API';
  const noBubbles = bubbles.length === 0;

  return (
    <form className="source-form" onSubmit={(e) => void onSubmit(e)} noValidate aria-labelledby={`${id}-title`}>
      <h3 id={`${id}-title`} className="form-title">
        {title}
      </h3>

      {duplicate && (
        <Notice tone="error" role="alert">
          Already added.{' '}
          <a href={`#source-${duplicate.id}`}>
            View the existing source
          </a>
        </Notice>
      )}

      <div className="field">
        <label className="field-label" htmlFor={`${id}-url`}>
          {kind === 'rss' ? 'Feed URL' : 'API URL'}
        </label>
        <input
          id={`${id}-url`}
          className="input"
          type="url"
          inputMode="url"
          autoComplete="off"
          value={url}
          readOnly={editing}
          aria-invalid={errors.url ? true : undefined}
          aria-describedby={errors.url ? `${id}-url-err` : `${id}-url-hint`}
          onChange={(e) => setUrl(e.target.value)}
        />
        {editing ? (
          <p id={`${id}-url-hint`} className="field-hint">The address cannot be changed. Add a new source for a different one.</p>
        ) : (
          <p id={`${id}-url-hint`} className="field-hint">Must start with http:// or https://</p>
        )}
        {errors.url && (
          <p id={`${id}-url-err`} className="field-error" role="alert">
            {errors.url}
          </p>
        )}
      </div>

      <fieldset className="field-group" aria-describedby={errors.bubbles ? `${id}-bubbles-err` : undefined}>
        <legend className="field-label">Bubbles</legend>
        {noBubbles ? (
          <p className="muted">
            There are no bubbles yet. <a href="/ui/bubbles">Create a bubble</a> first, then come back to add this source.
          </p>
        ) : (
          <div className="checkbox-grid">
            {bubbles.map((b) => (
              <label key={b.id} className="check-pill">
                <input
                  type="checkbox"
                  checked={bubbleIds.includes(b.id)}
                  onChange={(e) => toggleBubble(b.id, e.target.checked)}
                />
                <span>{b.name}</span>
              </label>
            ))}
          </div>
        )}
        {errors.bubbles && (
          <p id={`${id}-bubbles-err`} className="field-error" role="alert">
            {errors.bubbles}
          </p>
        )}
      </fieldset>

      {kind === 'api' && (
        <fieldset className="field-group">
          <legend className="field-label">How the response maps to items</legend>
          <p className="field-hint">
            JSONPath expressions. Items is evaluated on the response; the others on each item.
            {editing ? ' The mapping cannot be changed after the source is added.' : ''}
          </p>
          <PathField id={`${id}-items`} label="Items" value={itemsPath} onChange={setItemsPath} error={errors.items} required readOnly={editing} />
          <PathField id={`${id}-title-path`} label="Title (optional)" value={titlePath} onChange={setTitlePath} readOnly={editing} />
          <PathField id={`${id}-body`} label="Body" value={bodyPath} onChange={setBodyPath} error={errors.body} required readOnly={editing} />
          <PathField id={`${id}-date`} label="Date (optional)" value={datePath} onChange={setDatePath} readOnly={editing} />
          <PathField id={`${id}-link`} label="Link" value={urlPath} onChange={setUrlPath} error={errors.mapUrl} required readOnly={editing} />
          {editing ? (
            <p className="field-hint">
              Header names: {Object.keys(mapping?.headers ?? {}).join(', ') || 'none'}. Header values are write-only and cannot be changed here.
            </p>
          ) : (
            <div className="field">
              <span className="field-label">Headers (optional)</span>
              <p className="field-hint">Values are sent to the API and never shown again.</p>
              {headers.map((h, i) => (
                <div className="header-row" key={i}>
                  <input
                    className="input"
                    aria-label={`Header ${i + 1} name`}
                    placeholder="Name"
                    value={h.name}
                    onChange={(e) => setHeaders((prev) => prev.map((r, j) => (j === i ? { ...r, name: e.target.value } : r)))}
                  />
                  <input
                    className="input"
                    type="password"
                    autoComplete="off"
                    aria-label={`Header ${i + 1} value`}
                    placeholder="Value"
                    value={h.value}
                    onChange={(e) => setHeaders((prev) => prev.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))}
                  />
                  <button
                    type="button"
                    className="btn"
                    aria-label={`Remove header ${i + 1}`}
                    onClick={() => setHeaders((prev) => prev.filter((_, j) => j !== i))}
                  >
                    Remove
                  </button>
                </div>
              ))}
              <button type="button" className="btn btn-pill" onClick={() => setHeaders((prev) => [...prev, { name: '', value: '' }])}>
                Add header
              </button>
              {errors.headers && <p className="field-error" role="alert">{errors.headers}</p>}
            </div>
          )}
        </fieldset>
      )}

      <div className="form-grid">
        <div className="field">
          <label className="field-label" htmlFor={`${id}-poll`}>Check for updates</label>
          <select id={`${id}-poll`} className="input" value={poll} onChange={(e) => setPoll(e.target.value)}>
            {POLL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field-label" htmlFor={`${id}-cred`}>Credibility</label>
          <input
            id={`${id}-cred`}
            className="input"
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={credibility}
            aria-invalid={errors.credibility ? true : undefined}
            aria-describedby={`${id}-cred-hint`}
            onChange={(e) => setCredibility(e.target.value)}
          />
          <p id={`${id}-cred-hint`} className="field-hint">0 to 1. Default 0.5.</p>
          {errors.credibility && <p className="field-error" role="alert">{errors.credibility}</p>}
        </div>
        {kind === 'api' ? (
          <div className="field">
            <label className="field-label" htmlFor={`${id}-rate`}>Rate limit (items per hour)</label>
            <input
              id={`${id}-rate`}
              className="input"
              type="number"
              min={1}
              value={rate}
              aria-invalid={errors.rate ? true : undefined}
              onChange={(e) => setRate(e.target.value)}
            />
            {errors.rate && <p className="field-error" role="alert">{errors.rate}</p>}
          </div>
        ) : (
          <div className="field">
            <label className="field-label" htmlFor={`${id}-backfill`}>Backfill (days)</label>
            <input
              id={`${id}-backfill`}
              className="input"
              type="number"
              min={1}
              placeholder="Server default"
              value={backfill}
              aria-invalid={errors.backfill ? true : undefined}
              aria-describedby={`${id}-backfill-hint`}
              onChange={(e) => setBackfill(e.target.value)}
            />
            <p id={`${id}-backfill-hint`} className="field-hint">How far back to read the first time.</p>
            {errors.backfill && <p className="field-error" role="alert">{errors.backfill}</p>}
          </div>
        )}
      </div>

      <div className="form-checks">
        <label className="check-pill">
          <input type="checkbox" checked={fullText} onChange={(e) => setFullText(e.target.checked)} />
          <span>Store full text</span>
        </label>
        <label className="check-pill">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          <span>Enabled</span>
        </label>
      </div>

      {errors.save && (
        <Notice tone="error" role="alert">
          {errors.save}
        </Notice>
      )}

      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={busy !== null || noBubbles}>
          {busy === 'save' ? 'Saving…' : editing ? 'Save changes' : 'Add source'}
        </button>
        {!editing && (
          <button type="button" className="btn" onClick={() => void onTest()} disabled={busy !== null || noBubbles}>
            {busy === 'test' ? 'Testing…' : 'Test'}
          </button>
        )}
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
      </div>

      <div aria-live="polite" className="test-result">
        {testResult && (
          <div>
            <p>
              {testResult.items.length === 0
                ? 'The test found no items. Nothing was stored.'
                : `The test would ingest these first items. Nothing was stored (${testResult.items.length} shown):`}
            </p>
            {testResult.items.length > 0 && (
              <ul>
                {testResult.items.map((it, i) => (
                  <li key={`${it.url}-${i}`}>{it.title || it.url}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {testError && <p className="field-error">{testError}</p>}
      </div>
    </form>
  );
}

function PathField(props: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string | undefined;
  required?: boolean;
  readOnly?: boolean;
}): ReactElement {
  const { id, label, value, onChange, error, required, readOnly } = props;
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
        {required ? ' (required)' : ''}
      </label>
      <input
        id={id}
        className="input"
        value={value}
        autoComplete="off"
        spellCheck={false}
        readOnly={readOnly}
        aria-invalid={error ? true : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {error && <p className="field-error" role="alert">{error}</p>}
    </div>
  );
}
