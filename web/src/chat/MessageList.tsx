import { useMemo, type ReactElement } from 'react';
import type { Message, RunMode } from '@/api/types';
import { AnswerBlock } from './AnswerBlock';
import { RunBlock } from './RunBlock';
import type { RunWatch } from './useRunWatch';

interface MessageListProps {
  messages: readonly Message[];
  latestRunId: string | null;
  latestWatch: RunWatch;
  bubbleName: (id: string) => string | null;
  defaultMode: RunMode;
  onRetry: (question: string, mode: RunMode) => void;
}

/** The conversation: questions, their run status, and stored answers. */
export function MessageList(props: MessageListProps): ReactElement {
  const { messages, latestRunId, latestWatch, bubbleName, defaultMode, onRetry } = props;
  const answeredRunIds = useMemo(
    () => new Set(messages.filter((m) => m.role === 'assistant' && m.run_id).map((m) => m.run_id as string)),
    [messages],
  );

  if (messages.length === 0) {
    return <p className="muted thread-empty">No messages yet. Ask a question to start this conversation.</p>;
  }

  return (
    <ol className="thread" aria-label="Conversation">
      {messages.map((m) => {
        if (m.role === 'assistant') {
          return (
            <li key={m.id} className="msg msg-assistant">
              <AnswerBlock content={m.content} mode={m.mode ?? defaultMode} runId={m.run_id} />
            </li>
          );
        }
        const isLatest = m.run_id !== null && m.run_id === latestRunId;
        return (
          // Keyed by run so the optimistic copy and the stored copy are one item.
          <li key={m.run_id ? `run-${m.run_id}` : m.id} className="msg msg-user">
            <div className="user-bubble">
              <p>{m.content}</p>
            </div>
            {m.run_id && (
              <RunBlock
                runId={m.run_id}
                question={m.content}
                mode={m.mode ?? defaultMode}
                hasAnswerMessage={answeredRunIds.has(m.run_id)}
                bubbleName={bubbleName}
                onRetry={onRetry}
                {...(isLatest ? { watch: latestWatch } : {})}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
