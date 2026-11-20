import { useEffect, useId, useRef, useState, type FormEvent, type ReactElement } from 'react';
import { clearProviderKey, getProvider, saveProvider, testProvider } from '@/api/settings';
import { messageOf } from '@/api/client';
import type { ProviderSettings } from '@/api/types';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Notice } from '@/components/Notice';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useResource } from '@/hooks/useResource';
import { useBackgroundEffects } from '@/settings/prefs';

/** Which key is active, in words (spec 9). */
export function keySourceText(p: Pick<ProviderSettings, 'key_set' | 'key_source'>): string {
  if (p.key_source === 'ui') return 'Saved in OmniStream';
  if (p.key_source === 'env') return 'From environment (LLM_API_KEY)';
  return 'No key set';
}

function isHttpUrl(raw: string): boolean {
  try {
    const u = new URL(raw.trim());
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
}

/** Settings page (spec 9). The key is write-only and never comes back to the browser. */
export function SettingsPage(): ReactElement {
  useDocumentTitle('Settings');
  const provider = useResource((s) => getProvider(s), []);
  const [bgOn, setBgOn] = useBackgroundEffects();
  return (
    <div className="page settings-page">
      <h1 tabIndex={-1}>Settings</h1>
      <section className="settings-section" aria-labelledby="provider-heading">
        <h2 id="provider-heading">Provider</h2>
        <p className="muted">The model that writes answers. One active provider for now.</p>
        {provider.loading && !provider.data && <p className="muted" role="status">Loading provider…</p>}
        {provider.error && (
          <Notice tone="error" role="alert">
            Could not load provider settings. {messageOf(provider.error)}{' '}
            <button type="button" className="btn btn-pill" onClick={provider.reload}>
              Try again
            </button>
          </Notice>
        )}
        {provider.data && (
          <ProviderForm key={`${provider.data.base_url}|${provider.data.model}|${provider.data.key_hint}|${provider.data.key_source}`} initial={provider.data} onChanged={provider.setData} />
        )}
      </section>

      <section className="settings-section" aria-labelledby="display-heading">
        <h2 id="display-heading">Display</h2>
        <button
          type="button"
          role="switch"
          aria-checked={bgOn}
          className="switch"
          onClick={() => setBgOn(!bgOn)}
        >
          <span aria-hidden="true" className="switch-knob" />
          <span>Background effects: {bgOn ? 'On' : 'Off'}</span>
        </button>
        <p className="field-hint">The starfield on the home screen, with a twinkle, a swirl around the cursor and shooting stars. It always moves; switch it off here.</p>
      </section>
    </div>
  );
}

/**
 * The saved key is never sent to the browser, only its last four characters (when the server has
 * them). An environment key may have no hint at all, so the mask stands alone then.
 */
function maskedKeyText(hint: string | null | undefined): string {
  return hint ? `sk-••••${hint}` : 'sk-••••••••';
}

function maskedKeyReading(hint: string | null | undefined): string {
  return hint ? `key ending ${hint}` : 'API key is set';
}

function ProviderForm(props: {
  initial: ProviderSettings;
  onChanged: (next: ProviderSettings | ((prev: ProviderSettings | undefined) => ProviderSettings)) => void;
}): ReactElement {
  const { initial, onChanged } = props;
  const id = useId();
  const replaceRef = useRef<HTMLButtonElement>(null);
  const keyInputRef = useRef<HTMLInputElement>(null);
  const [baseUrl, setBaseUrl] = useState(initial.base_url);
  const [model, setModel] = useState(initial.model);
  const [keyEditing, setKeyEditing] = useState(!initial.key_set);
  const [newKey, setNewKey] = useState('');
  const [urlError, setUrlError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [current, setCurrent] = useState<ProviderSettings>(initial);
  // Focus moves after the render that shows the right control (see effect).
  const [focusTarget, setFocusTarget] = useState<'key' | 'replace' | null>(null);

  useEffect(() => {
    if (focusTarget === 'key') keyInputRef.current?.focus();
    if (focusTarget === 'replace') replaceRef.current?.focus();
    if (focusTarget !== null) setFocusTarget(null);
  }, [focusTarget]);

  function applyResult(next: ProviderSettings): void {
    setCurrent(next);
    onChanged(next);
  }

  async function onSave(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setSaved(null);
    setSaveError(null);
    if (!isHttpUrl(baseUrl)) {
      setUrlError('Enter an address that starts with http:// or https://.');
      return;
    }
    setUrlError(null);
    setSaving(true);
    try {
      const keyToSend = keyEditing && newKey.trim() ? newKey.trim() : undefined;
      const body = keyToSend !== undefined
        ? { api_key: keyToSend, base_url: baseUrl.trim(), model: model.trim() }
        : { base_url: baseUrl.trim(), model: model.trim() };
      const next = await saveProvider(body);
      applyResult(next);
      setNewKey('');
      setKeyEditing(false);
      setSaved('Settings saved.');
    } catch (err) {
      setSaveError(messageOf(err));
    } finally {
      setSaving(false);
    }
  }

  async function onClear(): Promise<void> {
    setConfirmClear(false);
    try {
      applyResult(await clearProviderKey());
      setKeyEditing(true);
      setSaved('Saved key cleared.');
    } catch (err) {
      setSaveError(messageOf(err));
    }
  }

  async function onTest(): Promise<void> {
    setTesting(true);
    setTestResult(null);
    try {
      setTestResult(await testProvider());
    } catch (err) {
      setTestResult({ ok: false, message: messageOf(err) });
    } finally {
      setTesting(false);
    }
  }

  return (
    <form className="provider-form" onSubmit={(e) => void onSave(e)} noValidate>
      <div className="key-block">
        <p className="field-label">API key</p>
        {current.key_set && !keyEditing ? (
          <div className="key-row">
            <span className="masked-key">
              <span aria-hidden="true">{maskedKeyText(current.key_hint)}</span>
              <span className="sr-only">{maskedKeyReading(current.key_hint)}</span>
            </span>
            <button
              ref={replaceRef}
              type="button"
              className="btn btn-pill"
              onClick={() => {
                setKeyEditing(true);
                setFocusTarget('key');
              }}
            >
              Replace key
            </button>
            {current.key_source === 'ui' && (
              <button type="button" className="btn btn-pill btn-danger" onClick={() => setConfirmClear(true)}>
                Clear key
              </button>
            )}
          </div>
        ) : (
          <div className="field">
            <label className="field-label" htmlFor={`${id}-key`}>
              {current.key_set ? 'New API key' : 'API key'}
            </label>
            <input
              ref={keyInputRef}
              id={`${id}-key`}
              className="input"
              type="password"
              autoComplete="new-password"
              spellCheck={false}
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              aria-describedby={`${id}-key-hint`}
            />
            <p id={`${id}-key-hint`} className="field-hint">
              Stored in OmniStream and never shown again. Leave blank to keep the current key.
            </p>
            {current.key_set && (
              <div className="run-actions">
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    setNewKey('');
                    setKeyEditing(false);
                    setFocusTarget('replace');
                  }}
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        )}
        <p className="key-source">{keySourceText(current)}</p>
      </div>

      <div className="field">
        <label className="field-label" htmlFor={`${id}-base`}>
          Base URL
        </label>
        <input
          id={`${id}-base`}
          className="input"
          type="url"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          aria-invalid={urlError ? true : undefined}
          aria-describedby={urlError ? `${id}-base-err` : `${id}-base-hint`}
        />
        <p id={`${id}-base-hint`} className="field-hint">OpenAI-compatible endpoint.</p>
        {urlError && (
          <p id={`${id}-base-err`} className="field-error" role="alert">
            {urlError}
          </p>
        )}
      </div>

      <div className="field">
        <label className="field-label" htmlFor={`${id}-model`}>
          Model name
        </label>
        <input id={`${id}-model`} className="input" value={model} onChange={(e) => setModel(e.target.value)} />
        <p className="field-hint">Test connection reports an unknown model name.</p>
      </div>

      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button type="button" className="btn" onClick={() => void onTest()} disabled={testing}>
          {testing ? 'Testing connection…' : 'Test connection'}
        </button>
      </div>

      <div aria-live="polite" className="settings-live">
        {saved && <Notice role="status">{saved}</Notice>}
        {saveError && (
          <Notice tone="error" role="alert">
            {saveError}
          </Notice>
        )}
        {testResult && (
          <Notice tone={testResult.ok ? 'default' : 'error'} role={testResult.ok ? 'status' : 'alert'}>
            {testResult.ok ? 'Connection works. ' : 'Connection failed. '}
            {testResult.message}
          </Notice>
        )}
      </div>

      <ConfirmDialog
        open={confirmClear}
        title="Clear the saved key?"
        description="OmniStream will use LLM_API_KEY from the environment if it is set. Otherwise questions cannot be answered."
        confirmLabel="Clear key"
        danger
        onConfirm={() => void onClear()}
        onCancel={() => setConfirmClear(false)}
      />
    </form>
  );
}
