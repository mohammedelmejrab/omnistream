import { useEffect, useState, type ReactElement } from 'react';
import { Link } from 'react-router';
import { getRunSteps } from '@/api/runs';
import { isNotFound } from '@/api/client';
import type { Citation, RunMode } from '@/api/types';
import { ModeBadge } from './ModeMarker';

interface AnswerBlockProps {
  content: string;
  mode: RunMode;
  runId: string | null;
}

/** Answer container (r-lg, spec 11). Plain text: no markup is interpreted. */
export function AnswerBlock({ content, mode, runId }: AnswerBlockProps): ReactElement {
  return (
    <article className="answer" aria-label="Answer">
      <header className="answer-head">
        <ModeBadge mode={mode} />
        <span className="answer-label">Answer</span>
        {runId && (
          <Link to={`/app/trace/${runId}`} className="trace-link">
            View trace
          </Link>
        )}
      </header>
      <div className="answer-body">{content}</div>
      {runId && <Citations runId={runId} />}
    </article>
  );
}

/** Numbered, cited sources for one run. Collected from its stored steps. */
export function Citations({ runId }: { runId: string }): ReactElement | null {
  const [citations, setCitations] = useState<Citation[]>([]);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getRunSteps(runId, controller.signal)
      .then((steps) => {
        const seen = new Set<string>();
        const ordered: Citation[] = [];
        const answerSteps = steps.filter((s) => s.kind === 'answer');
        for (const step of [...answerSteps, ...steps]) {
          for (const c of step.citations) {
            if (seen.has(c.item_id)) continue;
            seen.add(c.item_id);
            ordered.push(c);
          }
        }
        setCitations(ordered);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (isNotFound(err)) setExpired(true);
      });
    return () => controller.abort();
  }, [runId]);

  if (expired) {
    return <p className="muted trace-gone">Trace no longer available</p>;
  }
  if (citations.length === 0) return null;
  return (
    <section className="citations" aria-label="Sources used">
      <h3 className="citations-title">Sources</h3>
      <ol className="citation-list">
        {citations.map((c) => (
          <li key={c.item_id} className="citation-item">
            <a href={c.url} target="_blank" rel="noopener noreferrer">
              {c.title || c.url}
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          </li>
        ))}
      </ol>
    </section>
  );
}
