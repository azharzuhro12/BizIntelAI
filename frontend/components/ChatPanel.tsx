"use client";

/**
 * Panel AI Assistant (copilot kanan): POST /api/chat dengan session_id
 * per tab. Layout copilot penuh tinggi — header (status Online dari
 * /api/health, frontend fetch baru; backend tidak berubah), thread yang
 * menggulir sendiri, dan input yang tertaut di dasar kartu.
 *
 * Kontrak UI lama dipertahankan agar tes tetap bermakna: label input,
 * tombol "Kirim" (aria-label, tombol ikon panah), "Sesi baru", baris
 * "Sesi: ", chip tool dari tools_used aktual, dan "Sumber: [file.md]"
 * hasil parse citation (tidak pernah difabrikasi). Jawaban agent
 * dirender sebagai Markdown GFM (MarkdownMessage) — pesan user tetap
 * teks polos.
 */

import { Fragment, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { ApiError, getHealth, parseCitations, sendChat } from "@/lib/api";
import { MarkdownMessage } from "./MarkdownMessage";
import {
  adoptSessionId,
  getSessionIdSnapshot,
  resetSessionId,
  subscribeSession,
} from "@/lib/session";
import type { ChatMessage } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const SUGGESTIONS = [
  "Berapa total revenue dan jumlah transaksi?",
  "Prediksi revenue 3 hari ke depan",
  "Apa aturan promo yang berlaku?",
];

export function ChatPanel() {
  // session_id dari sessionStorage (null saat SSR / storage diblokir).
  const sessionId = useSyncExternalStore(
    subscribeSession,
    getSessionIdSnapshot,
    () => null,
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  // Status header: heartbeat backend (bukan metrik bisnis).
  const health = useApi(getHealth);
  const online =
    health.data !== null && health.data.status === "ok" && health.data.database === "connected";

  // Auto-scroll thread ke bawah saat pesan baru.
  useEffect(() => {
    const thread = threadRef.current;
    if (thread && typeof thread.scrollTo === "function") {
      thread.scrollTo({ top: thread.scrollHeight });
    }
  }, [messages, sending]);

  async function submit(question: string) {
    const message = question.trim();
    if (!message || sending || sessionId === null) return;
    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", text: message }]);
    setSending(true);
    try {
      const response = await sendChat({ message, session_id: sessionId });
      // Backend selalu meng-echo session_id yang dipakai; ikuti bila beda
      // agar turn berikutnya tetap nyambung di sesi yang benar.
      adoptSessionId(response.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: response.answer,
          toolsUsed: response.tools_used,
          citations: parseCitations(response.answer),
        },
      ]);
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause
          : new ApiError("network", "Terjadi kesalahan tak terduga saat mengirim pesan."),
      );
    } finally {
      setSending(false);
    }
  }

  function startNewSession() {
    if (sending) return;
    resetSessionId();
    setMessages([]);
    setError(null);
  }

  return (
    <section className="flex h-full min-h-0 flex-col rounded-xl border border-hairline bg-card p-4 shadow-sm sm:p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
            <span aria-hidden className="text-xs">
              ✨
            </span>
            AI Assistant
          </h2>
          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-secondary">
            <span
              aria-hidden
              className={`size-1.5 shrink-0 rounded-full ${
                health.initialLoading ? "bg-ink-muted" : online ? "bg-success" : "bg-series-2"
              }`}
            />
            {health.initialLoading ? "Memeriksa…" : online ? "Online" : "Offline"}
          </p>
        </div>
        <button
          type="button"
          onClick={startNewSession}
          disabled={sending}
          className="shrink-0 rounded-md border border-hairline px-3 py-1.5 text-xs text-ink-secondary transition-colors hover:bg-surface disabled:opacity-50"
        >
          Sesi baru
        </button>
      </div>

      <div
        ref={threadRef}
        aria-live="polite"
        className="min-h-40 flex-1 space-y-3 overflow-y-auto"
      >
        {messages.length === 0 && !sending ? (
          <div className="py-4 text-center">
            <p className="text-sm font-medium text-ink">
              Tanya apa saja tentang penjualan dan analisis data.
            </p>
            <p className="mt-1 text-xs text-ink-muted">Contoh pertanyaan:</p>
            <div className="mt-3 space-y-2 text-left">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => submit(suggestion)}
                  className="w-full rounded-lg border border-hairline bg-surface px-3 py-2 text-xs text-ink-secondary transition-colors hover:border-series-1/50 hover:text-ink"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {messages.map((message, index) => (
          <ChatBubble key={index} message={message} />
        ))}

        {sending ? (
          <div className="flex items-center gap-2 text-sm text-ink-secondary" role="status">
            <span
              aria-hidden
              className="inline-block size-4 animate-spin rounded-full border-2 border-hairline border-t-series-1"
            />
            Agent sedang berpikir…
          </div>
        ) : null}

        {error ? (
          <p
            className="rounded-md border border-series-2/40 bg-series-2/10 px-3 py-2 text-xs text-ink"
            role="alert"
          >
            {error.message}
            {error.code ? (
              <>
                {" "}
                <span className="font-mono text-ink-muted">({error.code})</span>
              </>
            ) : null}
          </p>
        ) : null}
      </div>

      <form
        className="mt-3 flex items-end gap-2 border-t border-hairline pt-3"
        onSubmit={(event) => {
          event.preventDefault();
          submit(input);
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Tulis pertanyaan bisnis…"
          aria-label="Pertanyaan untuk AI assistant"
          maxLength={2000}
          disabled={sending || sessionId === null}
          className="min-w-0 flex-1 rounded-lg border border-hairline bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-series-1 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          aria-label="Kirim"
          title="Kirim"
          disabled={sending || input.trim().length === 0 || sessionId === null}
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-lg bg-series-1 text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          <svg
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M12 19V5" />
            <path d="m5 12 7-7 7 7" />
          </svg>
        </button>
      </form>

      {sessionId ? (
        <p className="mt-2 font-mono text-[11px] text-ink-muted">Sesi: {sessionId}</p>
      ) : null}
    </section>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          isUser
            ? "max-w-[85%] rounded-xl rounded-br-sm bg-series-1/10 px-3 py-2 text-sm text-ink"
            : "max-w-[85%] rounded-xl rounded-bl-sm border border-hairline bg-surface px-3 py-2 text-sm text-ink"
        }
      >
        {/* Jawaban agent berformat Markdown GFM (tabel, bold, list); pesan
            user tetap teks polos apa adanya. */}
        {isUser ? <p className="whitespace-pre-wrap">{message.text}</p> : <MarkdownMessage text={message.text} />}
        {message.toolsUsed && message.toolsUsed.length > 0 ? (
          <div className="mt-2">
            <p className="text-[11px] text-ink-muted">Tools:</p>
            <p className="mt-1 flex flex-wrap gap-1.5">
              {message.toolsUsed.map((tool) => (
                <span
                  key={tool}
                  className="rounded-full border border-hairline bg-card px-2 py-0.5 font-mono text-[11px] text-ink-secondary"
                >
                  {tool}
                </span>
              ))}
            </p>
          </div>
        ) : null}
        {message.citations && message.citations.length > 0 ? (
          <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-secondary">
            Sumber:{" "}
            {message.citations.map((doc, index) => (
              <Fragment key={doc}>
                {index > 0 ? ", " : ""}
                <span className="rounded-full border border-series-1/30 bg-series-1/10 px-2 py-0.5 font-mono text-[11px] text-forecast">
                  {doc}
                </span>
              </Fragment>
            ))}
          </p>
        ) : null}
      </div>
    </div>
  );
}
