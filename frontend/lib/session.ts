/**
 * Sesi percakapan chat: satu session_id per tab browser (sessionStorage),
 * dipakai backend untuk memory multi-turn (agent_messages per sesi).
 * Charset aman kontrak backend: ^[A-Za-z0-9_.-]{1,128}$.
 *
 * Dibaca via useSyncExternalStore: snapshot server = null (SSR), snapshot
 * klien = id sesi tab; perubahan (reset/adopsi) memberi tahu subscriber.
 */

const STORAGE_KEY = "bizintel-chat-session-id";

const listeners = new Set<() => void>();

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify() {
  for (const listener of listeners) listener();
}

/** UUID v4 bila tersedia; fallback hex dari getRandomValues (charset sama). */
export function newSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Snapshot klien: ambil session_id tab ini; buat bila belum ada. */
export function getSessionIdSnapshot(): string | null {
  try {
    const existing = sessionStorage.getItem(STORAGE_KEY);
    if (existing && /^[A-Za-z0-9_.-]{1,128}$/.test(existing)) {
      return existing;
    }
    const fresh = newSessionId();
    sessionStorage.setItem(STORAGE_KEY, fresh);
    return fresh;
  } catch {
    // sessionStorage bisa diblok (private mode) - sesi in-memory saja.
    return null;
  }
}

/** Ganti sesi: id baru + kosongkan thread di UI (listener diberi tahu). */
export function resetSessionId(): string | null {
  const fresh = newSessionId();
  try {
    sessionStorage.setItem(STORAGE_KEY, fresh);
  } catch {
    return null;
  }
  notify();
  return fresh;
}

/** Ikuti session_id aktual dari respons backend bila berbeda. */
export function adoptSessionId(id: string): void {
  if (!/^[A-Za-z0-9_.-]{1,128}$/.test(id)) return;
  let changed = false;
  try {
    if (sessionStorage.getItem(STORAGE_KEY) !== id) {
      sessionStorage.setItem(STORAGE_KEY, id);
      changed = true;
    }
  } catch {
    return;
  }
  if (changed) notify();
}
