import { useCallback, useMemo, useRef, useState, type ReactElement } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router';
import { cancelRun } from '@/api/runs';
import { deleteChat, getChat, renameChat, sendMessage } from '@/api/chats';
import { getProvider } from '@/api/settings';
import { listBubbles } from '@/api/bubbles';
import { listSources } from '@/api/sources';
import { isNotFound, messageOf } from '@/api/client';
import type { Message, RunMode } from '@/api/types';
import { Composer } from '@/chat/Composer';
import { MessageList } from '@/chat/MessageList';
import { composeBlockReason } from '@/chat/blockReason';
import { readChatMode, writeChatMode } from '@/chat/chatMode';
import { resolveScope, type Mention } from '@/chat/mentions';
import { useRunWatch } from '@/chat/useRunWatch';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Notice } from '@/components/Notice';
import { notifyChatsChanged } from '@/hooks/chatsChanged';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useOnline } from '@/hooks/useOnline';
import { useRefetchOnFocus } from '@/hooks/useRefetchOnFocus';
import { useResource } from '@/hooks/useResource';
import { NotFoundPage } from './NotFoundPage';
import { SourcesSheet } from '@/sources/SourcesSheet';

/** Route element. Keyed by chat id so local state resets on every switch. */
export function ChatPage(): ReactElement {
  const { chatId = '' } = useParams();
  return <ChatView key={chatId} chatId={chatId} />;
}

function lastUserRunId(messages: readonly Message[]): string | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m && m.role === 'user' && m.run_id) return m.run_id;
  }
  return null;
}

function initialRunFromState(state: unknown): string | null {
  if (state && typeof state === 'object' && 'runId' in state) {
    const id = (state as { runId: unknown }).runId;
    return typeof id === 'string' ? id : null;
  }
  return null;
}

function ChatView({ chatId }: { chatId: string }): ReactElement {
  const navigate = useNavigate();
  const location = useLocation();
  const online = useOnline();
  const detail = useResource((s) => getChat(chatId, s), [chatId]);
  const bubbles = useResource((s) => listBubbles(s), []);
  const sources = useResource((s) => listSources(s), []);
  const provider = useResource((s) => getProvider(s), []);

  const [localRunId, setLocalRunId] = useState<string | null>(() => initialRunFromState(location.state));
  const [mode, setModeState] = useState<RunMode>(() => readChatMode(chatId));
  const [draft, setDraft] = useState('');
  const [mentions, setMentions] = useState<Mention[]>([]);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  const messages = useMemo(() => detail.data?.messages ?? [], [detail.data]);
  const latestRunId = lastUserRunId(messages) ?? localRunId;
  const latestWatch = useRunWatch(latestRunId, () => {
    // Finished: fetch the stored assistant message and refresh the rail.
    detail.reload();
    notifyChatsChanged();
  });
  const isRunning = latestWatch.run
    ? latestWatch.run.status === 'running'
    : latestRunId !== null && !latestWatch.error && !latestWatch.gone;

  const chat = detail.data?.chat;
  useDocumentTitle(chat ? chat.title : 'Conversation');
  // Two tabs on one chat: pick up messages stored by the other tab (spec 10.4).
  useRefetchOnFocus(detail.reload);

  const bubbleList = bubbles.data ?? [];
  const sourceList = sources.data ?? [];
  const bubbleName = useCallback(
    (id: string) => bubbleList.find((b) => b.id === id)?.name ?? null,
    [bubbleList],
  );
  const blockedReason = composeBlockReason({ online, provider: provider.data, bubbles: bubbles.data });

  async function send(content: string, sendMode: RunMode, bubbleIds: string[] | undefined): Promise<void> {
    setSending(true);
    setSendError(null);
    try {
      const body = bubbleIds ? { content, mode: sendMode, bubble_ids: bubbleIds } : { content, mode: sendMode };
      const res = await sendMessage(chatId, body);
      setLocalRunId(res.run_id);
      const optimistic: Message = {
        id: `local-${res.run_id}`,
        chat_id: chatId,
        role: 'user',
        content,
        run_id: res.run_id,
        mode: sendMode,
        created_at: new Date().toISOString(),
      };
      detail.setData((prev) => (prev ? { ...prev, messages: [...prev.messages, optimistic] } : prev));
      notifyChatsChanged();
    } catch (err) {
      setSendError(messageOf(err));
      throw err;
    } finally {
      setSending(false);
    }
  }

  async function onSend(): Promise<void> {
    const content = draft.trim();
    if (!content || isRunning) return;
    const scope = resolveScope(mentions, bubbleList, sourceList);
    if (scope.blocked) return;
    try {
      await send(content, mode, scope.bubbleIds);
      setDraft('');
      setMentions([]);
    } catch {
      composerRef.current?.focus();
    }
  }

  function onRetry(question: string, retryMode: RunMode): void {
    void send(question, retryMode, undefined).catch(() => undefined);
  }

  async function onStop(): Promise<void> {
    if (!latestRunId) return;
    try {
      await cancelRun(latestRunId);
    } catch (err) {
      setSendError(messageOf(err));
    }
  }

  function changeMode(next: RunMode): void {
    setModeState(next);
    writeChatMode(chatId, next);
  }

  async function saveRename(): Promise<void> {
    const title = renameValue.trim();
    if (!title) return;
    try {
      const updated = await renameChat(chatId, title);
      detail.setData((prev) => (prev ? { ...prev, chat: updated } : prev));
      setRenaming(false);
      notifyChatsChanged();
    } catch (err) {
      setSendError(messageOf(err));
    }
  }

  async function doDelete(): Promise<void> {
    try {
      await deleteChat(chatId);
      notifyChatsChanged();
      navigate('/app', { replace: true });
    } catch (err) {
      setSendError(messageOf(err));
      setConfirmDelete(false);
    }
  }

  if (detail.error && isNotFound(detail.error)) {
    return <NotFoundPage what="chat" />;
  }

  const heading = chat ? chat.title || 'Untitled chat' : 'Loading conversation';
  const loadFailed = detail.error && !isNotFound(detail.error);

  return (
    <div className="chat-page">
      <header className="chat-header">
        {renaming ? (
          <form
            className="rename-form"
            onSubmit={(e) => {
              e.preventDefault();
              void saveRename();
            }}
          >
            <label className="field">
              <span className="field-label">Chat name</span>
              <input
                className="input"
                value={renameValue}
                maxLength={120}
                onChange={(e) => setRenameValue(e.target.value)}
                autoFocus
              />
            </label>
            <div className="run-actions">
              <button type="submit" className="btn btn-primary" disabled={!renameValue.trim()}>
                Save name
              </button>
              <button type="button" className="btn" onClick={() => setRenaming(false)}>
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <>
            <h1 tabIndex={-1} className="chat-title">
              {heading}
            </h1>
            <div className="chat-actions">
              <button
                type="button"
                className="btn btn-pill"
                disabled={!chat}
                onClick={() => {
                  setRenameValue(chat?.title ?? '');
                  setRenaming(true);
                }}
              >
                Rename
              </button>
              <button type="button" className="btn btn-pill btn-danger" disabled={!chat} onClick={() => setConfirmDelete(true)}>
                Delete chat
              </button>
            </div>
          </>
        )}
      </header>

      {detail.loading && !detail.data && <p className="muted" role="status">Loading messages…</p>}
      {loadFailed && (
        <Notice tone="error" role="alert">
          Could not load this chat. {detail.error?.message}{' '}
          <button type="button" className="btn btn-pill" onClick={detail.reload}>
            Try again
          </button>
        </Notice>
      )}
      {sendError && (
        <Notice tone="error" role="alert">
          {sendError}
        </Notice>
      )}

      {detail.data && (
        <MessageList
          messages={messages}
          latestRunId={latestRunId}
          latestWatch={latestWatch}
          bubbleName={bubbleName}
          defaultMode={mode}
          onRetry={onRetry}
        />
      )}

      <div className="composer-dock">
        <Composer
          value={draft}
          onValueChange={setDraft}
          mode={mode}
          onModeChange={changeMode}
          bubbles={bubbleList}
          sources={sourceList}
          mentions={mentions}
          onMentionsChange={setMentions}
          blockedReason={sending ? null : blockedReason}
          running={isRunning || sending}
          onSend={() => void onSend()}
          onStop={() => void onStop()}
          onOpenSources={() => setSourcesOpen(true)}
          inputRef={composerRef}
        />
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this chat?"
        description="The chat and its messages are removed. Run traces stay available until they expire."
        confirmLabel="Delete chat"
        danger
        onConfirm={() => void doDelete()}
        onCancel={() => setConfirmDelete(false)}
      />
      <SourcesSheet open={sourcesOpen} onClose={() => setSourcesOpen(false)} />
    </div>
  );
}
