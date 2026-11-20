import { useCallback, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactElement } from 'react';
import { deleteSource, listSources, patchSource } from '@/api/sources';
import { messageOf } from '@/api/client';
import { listBubbles } from '@/api/bubbles';
import type { Source, SourceType } from '@/api/types';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Notice } from '@/components/Notice';
import { useResource } from '@/hooks/useResource';
import { DocumentUpload } from './DocumentUpload';
import { SourceForm } from './SourceForm';
import { SourceRow } from './SourceRow';
import { groupByBubble, sourceStatus } from './sourceStatus';
import { sourceLabel } from '@/chat/mentions';
import { Link } from 'react-router';

type TabKey = 'rss' | 'api' | 'document';
const TABS: readonly { key: TabKey; label: string; type: SourceType }[] = [
  { key: 'rss', label: 'Feeds', type: 'rss' },
  { key: 'api', label: 'APIs', type: 'api' },
  { key: 'document', label: 'Documents', type: 'document' },
];

type Pane =
  | { kind: 'list' }
  | { kind: 'add'; source?: undefined }
  | { kind: 'edit'; source: Source };

/**
 * Sources menu content (spec 8): Feeds, APIs and Documents, grouped by bubble.
 * Used inside the side sheet from "+" and on /app/sources.
 */
export function SourcesPanel({ onChanged }: { onChanged?: () => void }): ReactElement {
  const baseId = useId();
  const sources = useResource((s) => listSources(s), []);
  const bubbles = useResource((s) => listBubbles(s), []);
  const [tab, setTab] = useState<TabKey>('rss');
  const [pane, setPane] = useState<Pane>({ kind: 'list' });
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Source | null>(null);
  const [notice, setNotice] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null);
  const tabRefs = useRef<Record<TabKey, HTMLButtonElement | null>>({ rss: null, api: null, document: null });

  const all = useMemo(() => sources.data ?? [], [sources.data]);
  const bubbleList = useMemo(() => bubbles.data ?? [], [bubbles.data]);
  const bubbleIds = useMemo(() => new Set(bubbleList.map((b) => b.id)), [bubbleList]);
  const tabType = TABS.find((t) => t.key === tab)?.type ?? 'rss';
  const inTab = all.filter((s) => s.type === tabType);
  const groups = groupByBubble(inTab, bubbleList);

  const changed = useCallback(() => onChanged?.(), [onChanged]);

  function onTabKey(e: KeyboardEvent<HTMLButtonElement>): void {
    const idx = TABS.findIndex((t) => t.key === tab);
    let next = idx;
    if (e.key === 'ArrowRight') next = (idx + 1) % TABS.length;
    else if (e.key === 'ArrowLeft') next = (idx - 1 + TABS.length) % TABS.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = TABS.length - 1;
    else return;
    e.preventDefault();
    const target = TABS[next];
    if (!target) return;
    setTab(target.key);
    setPane({ kind: 'list' });
    tabRefs.current[target.key]?.focus();
  }

  async function toggle(source: Source): Promise<void> {
    setBusyId(source.id);
    try {
      const updated = await patchSource(source.id, { enabled: !source.enabled });
      sources.setData((prev) => (prev ?? []).map((s) => (s.id === updated.id ? updated : s)));
      setNotice({ tone: 'ok', text: `${updated.enabled ? 'Enabled' : 'Paused'} ${sourceLabel(updated)}.` });
      changed();
    } catch (err) {
      setNotice({ tone: 'error', text: messageOf(err) });
    } finally {
      setBusyId(null);
    }
  }

  async function confirmDelete(): Promise<void> {
    const target = deleting;
    if (!target) return;
    setBusyId(target.id);
    try {
      await deleteSource(target.id);
      sources.setData((prev) => (prev ?? []).filter((s) => s.id !== target.id));
      setNotice({ tone: 'ok', text: `Deleted ${sourceLabel(target)}.` });
      changed();
    } catch (err) {
      setNotice({ tone: 'error', text: messageOf(err) });
    } finally {
      setBusyId(null);
      setDeleting(null);
    }
  }

  function onSaved(source: Source, note: string): void {
    sources.setData((prev) => {
      const list = prev ?? [];
      return list.some((s) => s.id === source.id)
        ? list.map((s) => (s.id === source.id ? source : s))
        : [...list, source];
    });
    setNotice({ tone: 'ok', text: note });
    setHighlight(source.id);
    setPane({ kind: 'list' });
    changed();
  }

  const addKind: 'rss' | 'api' | null = tab === 'rss' ? 'rss' : tab === 'api' ? 'api' : null;
  const emptyTab = inTab.length === 0;

  return (
    <div className="sources-panel">
      <div className="tabs" role="tablist" aria-label="Source types">
        {TABS.map((t) => (
          <button
            key={t.key}
            ref={(el) => {
              tabRefs.current[t.key] = el;
            }}
            id={`${baseId}-tab-${t.key}`}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            aria-controls={`${baseId}-panel`}
            tabIndex={tab === t.key ? 0 : -1}
            className={tab === t.key ? 'tab tab-active' : 'tab'}
            onClick={() => {
              setTab(t.key);
              setPane({ kind: 'list' });
            }}
            onKeyDown={onTabKey}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div id={`${baseId}-panel`} role="tabpanel" aria-labelledby={`${baseId}-tab-${tab}`} className="tab-panel">
        {sources.loading && !sources.data && <p className="muted" role="status">Loading sources…</p>}
        {sources.error && (
          <Notice tone="error" role="alert">
            Could not load sources. {sources.error.message}{' '}
            <button type="button" className="btn btn-pill" onClick={sources.reload}>
              Try again
            </button>
          </Notice>
        )}

        {notice && (
          <Notice tone={notice.tone === 'error' ? 'error' : 'default'} role={notice.tone === 'error' ? 'alert' : 'status'}>
            {notice.text}
          </Notice>
        )}

        {pane.kind === 'list' && addKind && (
          <div className="pane-actions">
            <button
              type="button"
              className="btn btn-primary btn-pill"
              onClick={() => setPane({ kind: 'add' })}
            >
              {addKind === 'rss' ? 'Add a feed' : 'Add an API'}
            </button>
          </div>
        )}

        {pane.kind === 'add' && addKind && (
          <SourceForm
            kind={addKind}
            bubbles={bubbleList}
            existing={all}
            onSaved={onSaved}
            onCancel={() => setPane({ kind: 'list' })}
          />
        )}

        {pane.kind === 'edit' && (pane.source.type === 'rss' || pane.source.type === 'api') && (
          <SourceForm
            kind={pane.source.type}
            source={pane.source}
            bubbles={bubbleList}
            existing={all}
            onSaved={onSaved}
            onCancel={() => setPane({ kind: 'list' })}
          />
        )}

        {tab === 'document' && pane.kind !== 'edit' && (
          <DocumentUpload
            bubbles={bubbleList}
            onUploaded={() => {
              void sources.reload();
              changed();
            }}
          />
        )}

        {pane.kind === 'list' && tab !== 'document' && (
          <>
            {emptyTab && sources.data && (
              <div className="empty-state">
                <p>
                  {bubbleList.length === 0
                    ? 'There is nothing to add a source to yet. Create a bubble first.'
                    : tab === 'rss'
                      ? 'No feeds yet. Add one to start filling a bubble.'
                      : 'No APIs yet. Add one to start filling a bubble.'}
                </p>
                {bubbleList.length === 0 && (
                  <p>
                    <a href="/ui/bubbles">Create a bubble</a>
                  </p>
                )}
              </div>
            )}
            {groups.map((g) => (
              <section key={g.key} aria-label={`${g.title} bubble`} className="bubble-group">
                <h3 className="bubble-group-title">{g.title}</h3>
                <ul className="source-list">
                  {g.sources.map((s) => (
                    <SourceRow
                      key={s.id}
                      source={s}
                      name={sourceLabel(s)}
                      status={sourceStatus(s, bubbleIds)}
                      busy={busyId === s.id}
                      highlighted={highlight === s.id}
                      onToggle={(src) => void toggle(src)}
                      onEdit={(src) => {
                        setHighlight(null);
                        setPane({ kind: 'edit', source: src });
                      }}
                      onDelete={(src) => setDeleting(src)}
                    />
                  ))}
                </ul>
              </section>
            ))}
          </>
        )}

      </div>

      <ConfirmDialog
        open={deleting !== null}
        title="Delete this source?"
        description={
          deleting
            ? `${sourceLabel(deleting)} stops feeding its bubbles. Items already ingested stay in the graph.`
            : ''
        }
        confirmLabel="Delete source"
        danger
        busy={busyId !== null}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleting(null)}
      />

      <p className="sources-footer muted">
        Bubbles are created and edited on the <a href="/ui/bubbles">bubbles page</a>.
        {' '}
        <Link to="/app/graph">View the graph</Link>.
      </p>
    </div>
  );
}
