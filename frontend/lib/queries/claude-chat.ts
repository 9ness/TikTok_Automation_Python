"use client";

/**
 * Cliente del backend "Claude Chat" (Agent SDK en el host, ruta /claude-chat/*
 * via Caddy). Lista sesiones, carga el historial de una y streamea el chat
 * (SSE). Reusa NEXT_PUBLIC_API_URL + NEXT_PUBLIC_API_KEY (mismo gate admin).
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const BASE = api.baseUrl;
const KEY = process.env.NEXT_PUBLIC_API_KEY;

function headers(): Record<string, string> {
  return KEY ? { "X-API-Key": KEY } : {};
}

export interface ChatSession {
  id: string;
  project: string;
  title: string;
  last: string | null;
  turns: number;
  mtime: number;
  remote?: boolean;
  /** True si el chat está marcado como "arranca al reiniciar el server" —
   *  guardado en ~/.claude/remote_state/always_on.json, gestionado por el
   *  toggle 📌 en la UI. */
  always_on?: boolean;
}

/** Inyecta Remote Control a una sesión → aparece en la app de Claude (Code). */
export async function startRemote(
  sessionId: string,
  project: string,
): Promise<{ ok: boolean; remote: boolean; url?: string | null; msg?: string }> {
  const fd = new FormData();
  fd.append("session_id", sessionId);
  fd.append("project", project || "");
  const res = await fetch(`${BASE}/claude-chat/remote/start`, {
    method: "POST",
    headers: headers(),
    body: fd,
  });
  if (!res.ok) throw new Error(`remote ${res.status}`);
  return res.json();
}

export async function renameSession(
  sessionId: string,
  title: string,
): Promise<void> {
  const fd = new FormData();
  fd.append("session_id", sessionId);
  fd.append("title", title);
  await fetch(`${BASE}/claude-chat/rename`, {
    method: "POST",
    headers: headers(),
    body: fd,
  });
}

export async function stopRemote(sessionId: string): Promise<void> {
  const fd = new FormData();
  fd.append("session_id", sessionId);
  await fetch(`${BASE}/claude-chat/remote/stop`, {
    method: "POST",
    headers: headers(),
    body: fd,
  });
}

/** Activa Remote Control en TODOS los chats marcados always-on (o las 10
 *  más recientes si aún no hay pins). Idempotente: salta los ya activos.
 *  Devuelve resumen con contadores + resultados por chat. Tarda ~30-40s. */
export async function startAllRemote(): Promise<{
  ok: boolean;
  total_processed: number;
  started: number;
  already_active: number;
  failed: number;
  results: Array<{
    uuid: string;
    project: string;
    started: boolean;
    remote: boolean;
    url?: string | null;
    skipped_reason?: string;
    error?: string;
  }>;
}> {
  const res = await fetch(`${BASE}/claude-chat/remote/start-all`, {
    method: "POST",
    headers: headers(),
  });
  if (!res.ok) throw new Error(`start-all ${res.status}`);
  return res.json();
}

/** Toggle del pin 📌 de un chat: `enabled=true` lo añade a la lista de
 *  arranque, `enabled=false` lo saca. Persistente en always_on.json. */
export async function toggleAlwaysOn(
  sessionId: string,
  enabled: boolean,
): Promise<{ ok: boolean; always_on: boolean; total: number }> {
  const fd = new FormData();
  fd.append("session_id", sessionId);
  fd.append("enabled", String(enabled));
  const res = await fetch(`${BASE}/claude-chat/remote/always-on`, {
    method: "POST",
    headers: headers(),
    body: fd,
  });
  if (!res.ok) throw new Error(`always-on ${res.status}`);
  return res.json();
}
export interface SessionsResponse {
  projects: string[];
  sessions: ChatSession[];
}
export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}
export interface SessionDetail {
  id: string;
  project: string;
  messages: ChatMessage[];
}

export function useChatSessions() {
  return useQuery<SessionsResponse>({
    queryKey: ["claude-chat", "sessions"],
    queryFn: async () => {
      const res = await fetch(`${BASE}/claude-chat/sessions`, {
        headers: headers(),
      });
      if (!res.ok) throw new Error(`sessions ${res.status}`);
      return res.json();
    },
    staleTime: 15_000,
  });
}

export async function fetchSessionDetail(id: string): Promise<SessionDetail> {
  const res = await fetch(`${BASE}/claude-chat/session/${id}`, {
    headers: headers(),
  });
  if (!res.ok) throw new Error(`session ${res.status}`);
  return res.json();
}

export interface StreamHandlers {
  onSession?: (sessionId: string) => void;
  onText?: (chunk: string) => void;
  onDone?: () => void;
  onError?: (msg: string) => void;
}

/** Envía un turno y procesa el stream SSE. Devuelve un AbortController. */
export function streamChat(
  args: {
    message: string;
    project: string;
    sessionId?: string | null;
    images?: File[];
  },
  h: StreamHandlers,
): AbortController {
  const ctrl = new AbortController();
  const fd = new FormData();
  fd.append("message", args.message);
  fd.append("project", args.project || "");
  fd.append("session_id", args.sessionId || "");
  for (const img of args.images ?? []) fd.append("images", img);

  (async () => {
    try {
      const res = await fetch(`${BASE}/claude-chat/chat`, {
        method: "POST",
        headers: headers(),
        body: fd,
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        h.onError?.(`HTTP ${res.status}`);
        return;
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const blocks = buf.split("\n\n");
        buf = blocks.pop() ?? "";
        for (const block of blocks) {
          let ev = "message";
          let data = "";
          for (const line of block.split("\n")) {
            if (line.startsWith("event:")) ev = line.slice(6).trim();
            else if (line.startsWith("data:")) data += line.slice(5).trim();
          }
          if (!data) continue;
          let parsed: Record<string, unknown> = {};
          try {
            parsed = JSON.parse(data);
          } catch {
            continue;
          }
          if (ev === "session" && parsed.session_id)
            h.onSession?.(String(parsed.session_id));
          else if (ev === "text" && parsed.text)
            h.onText?.(String(parsed.text));
          else if (ev === "error")
            h.onError?.(String(parsed.error ?? "error"));
          else if (ev === "done") h.onDone?.();
        }
      }
      h.onDone?.();
    } catch (e) {
      if ((e as Error).name !== "AbortError")
        h.onError?.((e as Error).message);
    }
  })();

  return ctrl;
}
