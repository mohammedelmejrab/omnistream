import { useCallback, useSyncExternalStore } from 'react';

// Browser-side preferences (spec: mode per chat, background toggle).
// Values are JSON in localStorage; reads never throw (private mode, quota).

const listeners = new Set<() => void>();

function readRaw(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function readPreference<T>(key: string, fallback: T): T {
  const raw = readRaw(key);
  if (raw === null) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writePreference<T>(key: string, value: T): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage unavailable: the preference lasts for this page view only.
  }
  listeners.forEach((l) => l());
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

/** A localStorage-backed value that updates every component reading the same key. */
export function usePreference<T>(key: string, fallback: T): [T, (value: T) => void] {
  const snapshot = useSyncExternalStore(
    subscribe,
    () => readRaw(key),
    () => null,
  );
  const value = snapshot === null ? fallback : parseOr(snapshot, fallback);
  const set = useCallback((next: T) => writePreference(key, next), [key]);
  return [value, set];
}

function parseOr<T>(raw: string, fallback: T): T {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}
