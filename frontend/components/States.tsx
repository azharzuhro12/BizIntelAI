"use client";

/** State bersama semua widget: loading / error / kosong. */

export function LoadingState({ label = "Memuat data…" }: { label?: string }) {
  return (
    <div className="flex h-40 items-center justify-center gap-2 text-sm text-ink-secondary" role="status">
      <span
        aria-hidden
        className="inline-block size-4 animate-spin rounded-full border-2 border-hairline border-t-series-1"
      />
      {label}
    </div>
  );
}

export function ErrorState({
  message,
  code,
  onRetry,
}: {
  message: string;
  code?: string | null;
  onRetry: () => void;
}) {
  return (
    <div className="flex h-40 flex-col items-center justify-center gap-2 text-center" role="alert">
      <p className="text-sm text-ink">{message}</p>
      {code ? <p className="font-mono text-xs text-ink-muted">Kode: {code}</p> : null}
      <button
        type="button"
        onClick={onRetry}
        className="mt-1 rounded-md border border-hairline px-3 py-1.5 text-sm text-ink-secondary hover:bg-hairline/40"
      >
        Coba lagi
      </button>
    </div>
  );
}

export function EmptyState({ message = "Tidak ada data untuk ditampilkan." }: { message?: string }) {
  return (
    <div className="flex h-40 items-center justify-center text-sm text-ink-muted">{message}</div>
  );
}
