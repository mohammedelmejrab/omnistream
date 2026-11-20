import { useMemo, useRef, useState, type ReactElement } from 'react';
import { Link, useNavigate } from 'react-router';
import { createChat, listChats, sendMessage } from '@/api/chats';
import { listBubbles } from '@/api/bubbles';
import { listSources } from '@/api/sources';
import { getProvider } from '@/api/settings';
import { messageOf } from '@/api/client';
import type { RunMode } from '@/api/types';
import { Composer } from '@/chat/Composer';
import { composeBlockReason, titleFromQuestion } from '@/chat/blockReason';
import { readDefaultMode, writeChatMode, writeDefaultMode } from '@/chat/chatMode';
import { resolveScope, type Mention } from '@/chat/mentions';
import { StarBackground } from '@/background/StarBackground';
import { Notice } from '@/components/Notice';
import { notifyChatsChanged } from '@/hooks/chatsChanged';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useOnline } from '@/hooks/useOnline';
import { useResource } from '@/hooks/useResource';
import { useBackgroundEffects } from '@/settings/prefs';
import { SourcesSheet } from '@/sources/SourcesSheet';

export const SUGGESTIONS: readonly string[] = [
  'Summarise the latest EU energy policy changes',
  'What is new in bubble health?',
  'Compare what the sources say about tax changes',
];

/** Chat home (spec 6): empty chat, heading, input bar, suggestions and Recent. */
export function HomePage(): ReactElement {
  useDocumentTitle('Ask');
  const navigate = useNavigate();
  const online = useOnline();
  const provider = useResource((s) => getProvider(s), []);
  const bubbles = useResource((s) => listBubbles(s), []);
  const sources = useResource((s) => listSources(s), []);
  const chats = useResource((s) => listChats(s), []);
  const [bgOn] = useBackgroundEffects();
  const [draft, setDraft] = useState('');
  const [mentions, setMentions] = useState<Mention[]>([]);
  const [mode, setMode] = useState<RunMode>(() => readDefaultMode());
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);

  const bubbleList = useMemo(() => bubbles.data ?? [], [bubbles.data]);
  const sourceList = useMemo(() => sources.data ?? [], [sources.data]);
  const recent = (chats.data ?? []).slice(0, 3);
  const blockedReason = composeBlockReason({ online, provider: provider.data, bubbles: bubbles.data });

  async function onSend(): Promise<void> {
    const content = draft.trim();
    if (!content || sending) return;
    const scope = resolveScope(mentions, bubbleList, sourceList);
    if (scope.blocked) return;
    setSending(true);
    setError(null);
    try {
      const chat = await createChat(titleFromQuestion(content));
      writeChatMode(chat.id, mode);
      const body = scope.bubbleIds ? { content, mode, bubble_ids: scope.bubbleIds } : { content, mode };
      const res = await sendMessage(chat.id, body);
      notifyChatsChanged();
      navigate(`/app/chat/${chat.id}`, { state: { runId: res.run_id } });
    } catch (err) {
      setError(messageOf(err));
      setSending(false);
    }
  }

  return (
    <div className="home">
      <StarBackground enabled={bgOn} paused={sending} />
      <div className="home-column">
        <h1 tabIndex={-1} className="home-heading">
          Where should we start?
        </h1>
        <Composer
          value={draft}
          onValueChange={setDraft}
          mode={mode}
          onModeChange={(m) => {
            setMode(m);
            writeDefaultMode(m);
          }}
          bubbles={bubbleList}
          sources={sourceList}
          mentions={mentions}
          onMentionsChange={setMentions}
          blockedReason={blockedReason}
          running={sending}
          onSend={() => void onSend()}
          onStop={() => undefined}
          onOpenSources={() => setSourcesOpen(true)}
          inputRef={inputRef}
          autoFocus
        />
        {error && (
          <Notice tone="error" role="alert">
            {error}
          </Notice>
        )}
        <div className="chip-row suggestions" role="group" aria-label="Suggestions">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              className="chip"
              onClick={() => {
                setDraft(s);
                inputRef.current?.focus();
              }}
            >
              {s}
            </button>
          ))}
        </div>
        {recent.length > 0 && (
          <nav className="chip-row recent-row" aria-label="Recent chats">
            <span className="recent-label">Recent:</span>
            {recent.map((c) => (
              <Link key={c.id} to={`/app/chat/${c.id}`} className="chip">
                {c.title || 'Untitled chat'}
              </Link>
            ))}
            <Link to="/app/chats" className="chip chip-seeall">
              See all
            </Link>
          </nav>
        )}
      </div>
      <SourcesSheet open={sourcesOpen} onClose={() => setSourcesOpen(false)} />
    </div>
  );
}
