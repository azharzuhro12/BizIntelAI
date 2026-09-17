"use client";

/**
 * Wadah AI Assistant untuk layout dashboard (refinement Phase 6+):
 * - >= lg  : kolom kanan STICKY di grid dashboard — tetap terlihat saat
 *            widget dashboard digulir; ChatPanel menyediakan bingkai
 *            (border + rounded + surface) sendiri.
 * - < lg   : drawer kanan yang dibuka lewat tombol mengambang (layout
 *            mobile satu kolom penuh untuk dashboard).
 *
 * Hanya ada SATU instance <ChatPanel/> untuk kedua mode — state
 * percakapan dan session_id tidak terduplikasi antar breakpoint.
 * Semua interaksi lewat event handler (tanpa set-state-in-effect)
 * sesuai aturan eslint react-hooks (React Compiler) proyek ini.
 */

import { useRef, useState } from "react";

import { ChatPanel } from "./ChatPanel";

const PANEL_ID = "assistant-panel";

export function AssistantSidebar() {
  const [open, setOpen] = useState(false);
  const fabRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);

  function openDrawer() {
    setOpen(true);
    // ChatPanel selalu ter-mount (drawer digeser, bukan di-unmount),
    // jadi input langsung bisa difokuskan tanpa menunggu render.
    const input = panelRef.current?.querySelector<HTMLInputElement>("input");
    input?.focus();
  }

  function closeDrawer() {
    setOpen(false);
    fabRef.current?.focus();
  }

  return (
    // Satu root = satu grid item. Di >= lg wrapper inilah kolom sticky
    // dengan tinggi penuh sisa viewport di bawah navigasi atas (h-14 +
    // jarak); ChatPanel mengelola gulir internalnya sendiri.
    // Di < lg wrapper kosong dari flow (anak-anaknya position: fixed).
    <div className="lg:sticky lg:top-[4.5rem] lg:h-[calc(100dvh-6rem)] lg:self-start">
      {/* Tombol mengambang pembuka drawer (khusus layout < lg). */}
      <button
        ref={fabRef}
        type="button"
        onClick={openDrawer}
        aria-label="Buka AI Assistant"
        aria-expanded={open}
        aria-controls={PANEL_ID}
        className={`fixed bottom-5 right-5 z-50 inline-flex items-center gap-2 rounded-full bg-series-1 px-4 py-3 text-sm font-medium text-white shadow-lg hover:opacity-90 lg:hidden ${
          open ? "hidden" : ""
        }`}
      >
        <span aria-hidden className="text-base leading-none">
          ✦
        </span>
        AI Assistant
      </button>

      {/* Backdrop penutup drawer (klik = tutup). */}
      {open ? (
        <button
          type="button"
          aria-label="Tutup panel AI Assistant"
          onClick={closeDrawer}
          className="fixed inset-0 z-30 bg-ink/30 lg:hidden"
        />
      ) : null}

      {/* Satu node untuk dua mode: drawer fixed di < lg, blok normal
          (di dalam wrapper sticky) di >= lg. */}
      <aside
        id={PANEL_ID}
        ref={panelRef}
        aria-label="AI Assistant"
        onKeyDown={(event) => {
          if (event.key === "Escape" && open) closeDrawer();
        }}
        className={[
          "fixed top-0 bottom-0 right-0 z-40 flex w-[min(22rem,88vw)] flex-col border-l border-hairline bg-surface p-2 shadow-xl transition-transform duration-200",
          open ? "translate-x-0" : "translate-x-full",
          // >= lg: drawer menjadi blok biasa dalam wrapper sticky;
          // bingkai visual diambil alih oleh section ChatPanel sendiri.
          "lg:static lg:z-auto lg:h-full lg:w-full lg:translate-x-0 lg:flex lg:flex-col lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none lg:transition-none",
        ].join(" ")}
      >
        {/* Header drawer mobile; judul semantik sudah ada di <h2> ChatPanel. */}
        <div className="mb-1 flex items-center justify-between gap-2 px-3 pt-2 lg:hidden">
          <span aria-hidden className="text-sm font-semibold text-ink">
            AI Assistant
          </span>
          <button
            type="button"
            onClick={closeDrawer}
            aria-label="Tutup AI Assistant"
            className="rounded-md border border-hairline px-2.5 py-1 text-xs text-ink-secondary hover:bg-hairline/40"
          >
            Tutup
          </button>
        </div>

        <div className="min-h-0 flex-1">
          <ChatPanel />
        </div>
      </aside>
    </div>
  );
}
