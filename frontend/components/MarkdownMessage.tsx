"use client";

/**
 * Render jawaban AI Assistant sebagai Markdown GFM (tabel, bold/italic,
 * list, heading, kode, tautan) agar sesuai bahasa respons agent.
 * Aman secara default: TANPA rehype-raw — HTML mentah tidak dieksekusi;
 * urlTransform bawaan react-markdown hanya mengizinkan skema aman.
 * Tautan eksternal dibuka di tab baru (noopener noreferrer).
 * Tabel dibungkus overflow-x-auto supaya melebar ke bawah, bukan menyebabkan
 * overflow halaman.
 */

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// Kelas pengganti <code> inline di dalam <pre> (blok kode) — CSS-only,
// tanpa deteksi JS block/inline.
const markdownComponents: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-4">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-4">{children}</ol>,
  h1: ({ children }) => <h1 className="mb-2 mt-1 text-base font-semibold text-ink">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-1 text-sm font-semibold text-ink">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1 mt-1 text-sm font-semibold text-ink">{children}</h3>,
  h4: ({ children }) => <h4 className="mb-1 mt-1 text-sm font-semibold text-ink">{children}</h4>,
  h5: ({ children }) => <h5 className="mb-1 mt-1 text-sm font-semibold text-ink">{children}</h5>,
  h6: ({ children }) => <h6 className="mb-1 mt-1 text-sm font-semibold text-ink">{children}</h6>,
  code: ({ children }) => (
    <code className="rounded border border-hairline bg-surface px-1 py-0.5 font-mono text-xs text-ink-secondary">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <div className="my-2 w-full max-w-full overflow-x-auto rounded-lg border border-hairline bg-surface p-2">
      <pre className="font-mono text-xs leading-relaxed text-ink [&>code]:rounded-none [&>code]:border-0 [&>code]:bg-transparent [&>code]:px-0 [&>code]:py-0 [&>code]:text-ink">
        {children}
      </pre>
    </div>
  ),
  // style (textAlign) diteruskan agar alignment kolom GFM (---:) bekerja.
  table: ({ children }) => (
    <div className="my-2 w-full max-w-full overflow-x-auto rounded-lg border border-hairline">
      <table className="w-full border-collapse text-left text-xs">{children}</table>
    </div>
  ),
  th: ({ children, style }) => (
    <th
      style={style}
      className="whitespace-nowrap border-b border-hairline bg-surface px-2 py-1.5 font-semibold text-ink"
    >
      {children}
    </th>
  ),
  td: ({ children, style }) => (
    <td style={style} className="border-b border-hairline/60 px-2 py-1.5 align-top text-ink-secondary">
      {children}
    </td>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="break-all text-series-1 underline underline-offset-2"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-hairline pl-2 text-ink-secondary">{children}</blockquote>
  ),
  hr: () => <hr className="my-2 border-hairline" />,
};

export function MarkdownMessage({ text }: { text: string }) {
  return (
    <div className="min-w-0 text-sm text-ink">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
