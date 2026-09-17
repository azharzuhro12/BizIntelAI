/** Test penanganan session_id chat (sessionStorage per tab + store). */

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  adoptSessionId,
  getSessionIdSnapshot,
  newSessionId,
  resetSessionId,
  subscribeSession,
} from "@/lib/session";

const SESSION_ID_RE = /^[A-Za-z0-9_.-]{1,128}$/;

beforeEach(() => {
  sessionStorage.clear();
});

describe("newSessionId", () => {
  it("menghasilkan id sesuai charset kontrak backend", () => {
    for (let i = 0; i < 20; i++) {
      expect(newSessionId()).toMatch(SESSION_ID_RE);
    }
  });

  it("jarang identik antar panggilan", () => {
    const ids = new Set(Array.from({ length: 20 }, () => newSessionId()));
    expect(ids.size).toBeGreaterThan(15);
  });
});

describe("getSessionIdSnapshot", () => {
  it("membuat dan menyimpan id saat belum ada", () => {
    const id = getSessionIdSnapshot();
    expect(id).toMatch(SESSION_ID_RE);
    expect(sessionStorage.getItem("bizintel-chat-session-id")).toBe(id);
  });

  it("id sama pada panggilan berikutnya (satu sesi per tab)", () => {
    const first = getSessionIdSnapshot();
    expect(getSessionIdSnapshot()).toBe(first);
  });

  it("id tersimpan yang tidak valid diganti", () => {
    sessionStorage.setItem("bizintel-chat-session-id", "../.env");
    const id = getSessionIdSnapshot();
    expect(id).not.toBe("../.env");
    expect(id).toMatch(SESSION_ID_RE);
  });
});

describe("resetSessionId", () => {
  it("menghasilkan id baru, mengganti nilai tersimpan, dan memberi tahu subscriber", () => {
    const old = getSessionIdSnapshot();
    const notified = vi.fn();
    const unsubscribe = subscribeSession(notified);

    const fresh = resetSessionId();
    expect(fresh).not.toBe(old);
    expect(fresh).toMatch(SESSION_ID_RE);
    expect(sessionStorage.getItem("bizintel-chat-session-id")).toBe(fresh);
    expect(getSessionIdSnapshot()).toBe(fresh);
    expect(notified).toHaveBeenCalled();

    unsubscribe();
  });

  it("id baru tetap acak setelah beberapa reset", () => {
    const ids = new Set([resetSessionId(), resetSessionId(), resetSessionId()]);
    expect(ids.size).toBe(3);
  });
});

describe("adoptSessionId", () => {
  it("menyimpan id valid baru dan memberi tahu subscriber", () => {
    const notified = vi.fn();
    const unsubscribe = subscribeSession(notified);
    adoptSessionId("backend-echo-42");
    expect(sessionStorage.getItem("bizintel-chat-session-id")).toBe("backend-echo-42");
    expect(notified).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("id yang sudah sama tidak memicu notifikasi", () => {
    getSessionIdSnapshot();
    const current = sessionStorage.getItem("bizintel-chat-session-id");
    const notified = vi.fn();
    const unsubscribe = subscribeSession(notified);
    adoptSessionId(current as string);
    expect(notified).not.toHaveBeenCalled();
    unsubscribe();
  });

  it("menolak id di luar charset kontrak", () => {
    getSessionIdSnapshot();
    const before = sessionStorage.getItem("bizintel-chat-session-id");
    adoptSessionId("../.env");
    expect(sessionStorage.getItem("bizintel-chat-session-id")).toBe(before);
  });
});
