import { useId, useState, type ReactElement } from 'react';
import { Link } from 'react-router';
import { deleteChat, listChats, renameChat } from '@/api/chats';
import { messageOf } from '@/api/client';
import type { Chat } from '@/api/types';
import { ModeBadge } from '@/chat/ModeMarker';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Notice } from '@/components/Notice';
import { notifyChatsChanged, useChatsChanged } from '@/hooks/chatsChanged';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useResource } from '@/hooks/useResource';
import { formatWhen } from '@/sources/sourceStatus';

/** /app/chats: every chat, with rename and delete (spec 10.6). */
export function ChatsPage(): ReactElement {
  useDocumentTitle('All chats');
  const chats = useResource((s) => listChats(s), []);
  useChatsChanged(chats.reload);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [deleting, setDeleting] = useState<Chat | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const listId = useId();

  async function saveRename(chat: Chat): Promise<void> {
    const title = renameValue.trim();
    if (!title) return;
    setBusy(true);
    try {
      const updated = await renameChat(chat.id, title);
      chats.setData((prev) => (prev ?? []).map((c) => (c.id === updated.id ? updated : c)));
      setRenamingId(null);
      notifyChatsChanged();
    } catch (err) {
      setNotice(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete(): Promise<void> {
    const target = deleting;
    if (!target) return;
    setBusy(true);
    try {
      await deleteChat(target.id);
      chats.setData((prev) => (prev ?? []).filter((c) => c.id !== target.id));
      notifyChatsChanged();
    } catch (err) {
      setNotice(messageOf(err));
    } finally {
      setBusy(false);
      setDeleting(null);
    }
  }

  const list = chats.data ?? [];
  return (
    <div className="page">
      <h1 tabIndex={-1}>All chats</h1>
      {notice && (
        <Notice tone="error" role="alert">
          {notice}
        </Notice>
      )}
      {chats.loading && !chats.data && <p className="muted" role="status">Loading chats…</p>}
      {chats.error && (
        <Notice tone="error" role="alert">
          Could not load chats. <button type="button" className="btn btn-pill" onClick={chats.reload}>Try again</button>
        </Notice>
      )}
      {chats.data && list.length === 0 && (
        <div className="empty-state">
          <p>No chats yet. Start one from the home screen.</p>
          <p>
            <Link to="/app" className="btn btn-primary btn-pill">
              Start a chat
            </Link>
          </p>
        </div>
      )}
      <ul className="chat-list" id={listId}>
        {list.map((c) => (
          <li key={c.id} className="chat-row">
            {renamingId === c.id ? (
              <form
                className="rename-inline"
                onSubmit={(e) => {
                  e.preventDefault();
                  void saveRename(c);
                }}
              >
                <label className="field">
                  <span className="field-label">Chat name</span>
                  <input className="input" value={renameValue} maxLength={120} autoFocus onChange={(e) => setRenameValue(e.target.value)} />
                </label>
                <div className="run-actions">
                  <button type="submit" className="btn btn-primary" disabled={busy || !renameValue.trim()}>
                    Save name
                  </button>
                  <button type="button" className="btn" onClick={() => setRenamingId(null)}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <>
                <div className="chat-row-main">
                  <Link to={`/app/chat/${c.id}`} className="chat-row-title">
                    {c.title || 'Untitled chat'}
                  </Link>
                  <span className="muted">
                    Updated {formatWhen(c.updated_at)} · <ModeBadge mode={c.mode} />
                  </span>
                </div>
                <div className="chat-row-actions">
                  <button
                    type="button"
                    className="btn btn-pill"
                    onClick={() => {
                      setRenameValue(c.title);
                      setRenamingId(c.id);
                    }}
                  >
                    Rename<span className="sr-only"> {c.title}</span>
                  </button>
                  <button type="button" className="btn btn-pill btn-danger" onClick={() => setDeleting(c)}>
                    Delete<span className="sr-only"> {c.title}</span>
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={deleting !== null}
        title="Delete this chat?"
        description="The chat and its messages are removed. Run traces stay available until they expire."
        confirmLabel="Delete chat"
        danger
        busy={busy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
