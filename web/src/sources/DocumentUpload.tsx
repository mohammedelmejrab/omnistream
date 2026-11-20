import { useId, useRef, useState, type DragEvent, type FormEvent, type ReactElement } from 'react';
import { uploadDocument, type UploadProgress } from '@/api/sources';
import { ApiError, NetworkError } from '@/api/client';
import type { Bubble, IngestResult } from '@/api/types';
import { Notice } from '@/components/Notice';
import { DOCUMENT_EXTENSIONS, checkDocumentFile, uploadErrorMessage } from './validation';

interface DocumentUploadProps {
  bubbles: readonly Bubble[];
  onUploaded: (results: IngestResult[]) => void;
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'uploading'; progress: UploadProgress | null }
  | { kind: 'done'; results: IngestResult[] }
  | { kind: 'error'; message: string };

/**
 * Document upload (spec 8). A real file input is the keyboard path; drag and
 * drop is an addition, never the only way in.
 */
export function DocumentUpload({ bubbles, onUploaded }: DocumentUploadProps): ReactElement {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [bubbleIds, setBubbleIds] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const [bubbleError, setBubbleError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  function pick(candidate: File | undefined): void {
    setFileError(null);
    if (!candidate) return;
    const check = checkDocumentFile(candidate);
    if (!check.ok) {
      setFile(null);
      setFileError(check.message);
      return;
    }
    setFile(candidate);
    setPhase({ kind: 'idle' });
  }

  function onDrop(e: DragEvent<HTMLDivElement>): void {
    e.preventDefault();
    setDragOver(false);
    pick(e.dataTransfer.files[0]);
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    if (!file) {
      setFileError('Choose a file first.');
      return;
    }
    if (bubbleIds.length === 0) {
      setBubbleError('Choose at least one bubble for this document.');
      return;
    }
    setBubbleError(null);
    setPhase({ kind: 'uploading', progress: null });
    try {
      const results = await uploadDocument({
        file,
        bubbleIds,
        credibility: 0.5,
        onProgress: (progress) => setPhase({ kind: 'uploading', progress }),
      });
      setPhase({ kind: 'done', results });
      setFile(null);
      if (inputRef.current) inputRef.current.value = '';
      onUploaded(results);
    } catch (err) {
      let message = 'The upload failed. Try again.';
      if (err instanceof NetworkError) message = 'OmniStream server is unreachable. Your file is still selected.';
      else if (err instanceof ApiError) message = uploadErrorMessage(err.status, err.message);
      setPhase({ kind: 'error', message });
    }
  }

  const uploading = phase.kind === 'uploading';
  const pct = phase.kind === 'uploading' && phase.progress && phase.progress.total > 0
    ? Math.round((phase.progress.loaded / phase.progress.total) * 100)
    : 0;
  const accept = DOCUMENT_EXTENSIONS.join(',');

  return (
    <form className="doc-upload" onSubmit={(e) => void onSubmit(e)} noValidate>
      <h3 className="form-title">Add a document</h3>
      <div
        className={dragOver ? 'dropzone dropzone-over' : 'dropzone'}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <p>{file ? `Selected: ${file.name}` : 'Drop a file here, or choose one below.'}</p>
        <p className="field-hint">Accepted: .pdf, .docx, .txt, .md</p>
      </div>
      <div className="field">
        <label className="field-label" htmlFor={`${id}-file`}>
          Document file
        </label>
        <input
          ref={inputRef}
          id={`${id}-file`}
          type="file"
          accept={accept}
          className="input"
          aria-invalid={fileError ? true : undefined}
          aria-describedby={fileError ? `${id}-file-err` : undefined}
          onChange={(e) => pick(e.target.files?.[0])}
        />
        {fileError && (
          <p id={`${id}-file-err`} className="field-error" role="alert">
            {fileError}
          </p>
        )}
      </div>

      <fieldset className="field-group" aria-describedby={bubbleError ? `${id}-bub-err` : undefined}>
        <legend className="field-label">Bubbles</legend>
        {bubbles.length === 0 ? (
          <p className="muted">
            There are no bubbles yet. <a href="/ui/bubbles">Create a bubble</a> first.
          </p>
        ) : (
          <div className="checkbox-grid">
            {bubbles.map((b) => (
              <label key={b.id} className="check-pill">
                <input
                  type="checkbox"
                  checked={bubbleIds.includes(b.id)}
                  onChange={(e) =>
                    setBubbleIds((prev) => (e.target.checked ? [...prev, b.id] : prev.filter((x) => x !== b.id)))
                  }
                />
                <span>{b.name}</span>
              </label>
            ))}
          </div>
        )}
        {bubbleError && (
          <p id={`${id}-bub-err`} className="field-error" role="alert">
            {bubbleError}
          </p>
        )}
      </fieldset>

      {uploading && (
        <div className="progress-wrap">
          <p className="field-label">Uploading {pct}%</p>
          <div
            id={`${id}-progress`}
            role="progressbar"
            aria-label="Upload progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            className="progress"
          >
            <span style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={uploading || bubbles.length === 0}>
          {uploading ? 'Uploading…' : 'Upload document'}
        </button>
      </div>

      <div aria-live="polite">
        {phase.kind === 'done' && (
          <Notice role="status">
            {summarise(phase.results)}
          </Notice>
        )}
        {phase.kind === 'error' && (
          <Notice tone="error" role="alert">
            {phase.message}
          </Notice>
        )}
      </div>
    </form>
  );
}

function summarise(results: readonly IngestResult[]): string {
  const queued = results.filter((r) => r.status === 'queued').length;
  const dupes = results.length - queued;
  if (results.length === 0) return 'The file was read but contained no text to ingest.';
  const parts = [`Parsed. ${queued} ${queued === 1 ? 'part' : 'parts'} queued for the graph.`];
  if (dupes > 0) parts.push(`${dupes} already known and skipped.`);
  return parts.join(' ');
}
