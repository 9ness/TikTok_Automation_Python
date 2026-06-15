"use client";

import {
  ImagePlus,
  Loader2,
  MessageSquarePlus,
  PanelLeft,
  Pencil,
  Send,
  Smartphone,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  type ChatMessage,
  type ChatSession,
  fetchSessionDetail,
  renameSession,
  startRemote,
  streamChat,
  useChatSessions,
} from "@/lib/queries/claude-chat";

function timeAgo(ts: number): string {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "ahora";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export default function ClaudeChatPage() {
  const sessionsQ = useChatSessions();
  const projects = sessionsQ.data?.projects ?? [];
  const sessions = sessionsQ.data?.sessions ?? [];

  const [project, setProject] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [showList, setShowList] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [remoting, setRemoting] = useState(false);
  const [remoteMsg, setRemoteMsg] = useState<string | null>(null);
  const [remoteUrl, setRemoteUrl] = useState<string | null>(null);

  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!project && projects.length) setProject(projects[0] ?? "");
  }, [projects, project]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  async function openSession(id: string, proj: string) {
    setShowList(false);
    setErr(null);
    setSessionId(id);
    setProject(proj);
    setMessages([{ role: "assistant", text: "Cargando…" }]);
    try {
      const d = await fetchSessionDetail(id);
      setMessages(d.messages);
    } catch {
      setMessages([]);
      setErr("No se pudo cargar el chat.");
    }
  }

  async function doRename(s: ChatSession) {
    const name = window.prompt("Nombre del chat:", s.title);
    if (name === null) return;
    try {
      await renameSession(s.id, name.trim());
      sessionsQ.refetch();
    } catch {
      setErr("No se pudo renombrar.");
    }
  }

  function newChat() {
    setSessionId(null);
    setMessages([]);
    setErr(null);
    setShowList(false);
  }

  async function doRemote() {
    if (!sessionId || remoting) return;
    setRemoting(true);
    setRemoteMsg(null);
    setRemoteUrl(null);
    try {
      const r = await startRemote(sessionId, project);
      setRemoteUrl(r.url ?? null);
      setRemoteMsg(
        r.remote
          ? "✅ Activado en la app. Abre este chat en el móvil:"
          : "⚠️ No se pudo activar el control remoto. Reinténtalo.",
      );
    } catch {
      setRemoteMsg("⚠️ Error activando el control remoto.");
    } finally {
      setRemoting(false);
    }
  }

  function send() {
    const text = input.trim();
    if ((!text && images.length === 0) || streaming) return;
    setErr(null);
    const userMsg: ChatMessage = {
      role: "user",
      text: text + (images.length ? ` 📎${images.length}` : ""),
    };
    setMessages((m) => [...m, userMsg, { role: "assistant", text: "" }]);
    const imgs = images;
    setInput("");
    setImages([]);
    setStreaming(true);

    streamChat(
      { message: text, project, sessionId, images: imgs },
      {
        onSession: (sid) => setSessionId(sid),
        onText: (chunk) =>
          setMessages((m) => {
            const copy = [...m];
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = {
              role: "assistant",
              text: (last?.text ?? "") + chunk,
            };
            return copy;
          }),
        onError: (msg) => {
          setErr(msg);
          setStreaming(false);
        },
        onDone: () => {
          setStreaming(false);
          sessionsQ.refetch();
        },
      },
    );
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col md:h-screen">
      {/* Barra superior — botones a la IZQUIERDA (siempre visibles); el
          selector de proyecto a la derecha. `md:pr-28` deja hueco al badge
          "Cola" (fixed right-3 top-3) del layout para que no tape nada. */}
      <header className="flex items-center gap-2 border-b p-2 sm:p-3 md:pr-28">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowList((v) => !v)}
          className="shrink-0"
        >
          <PanelLeft className="h-4 w-4" />
          <span className="ml-1 hidden sm:inline">Chats</span>
        </Button>
        <Button size="sm" onClick={newChat} className="shrink-0">
          <MessageSquarePlus className="h-4 w-4" />
          <span className="ml-1 hidden sm:inline">Nuevo</span>
        </Button>
        <Button
          variant={sessionId ? "default" : "secondary"}
          size="sm"
          className="shrink-0"
          onClick={doRemote}
          disabled={!sessionId || remoting}
          title="Activar este chat en la app del móvil (control remoto)"
        >
          {remoting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Smartphone className="h-4 w-4" />
          )}
          <span className="ml-1 hidden sm:inline">A la app</span>
        </Button>
        <select
          value={project}
          onChange={(e) => setProject(e.target.value)}
          className="min-w-0 flex-1 truncate rounded-md border bg-background px-2 py-1.5 text-xs sm:text-sm"
        >
          {projects.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </header>

      <div className="relative flex min-h-0 flex-1">
        {/* Lista de chats */}
        {showList && (
          <button
            type="button"
            aria-label="cerrar"
            className="absolute inset-0 z-10 bg-black/30 md:hidden"
            onClick={() => setShowList(false)}
          />
        )}
        <aside
          className={`${
            showList ? "block" : "hidden"
          } absolute z-20 h-full w-72 max-w-[85vw] overflow-y-auto border-r bg-background md:static md:z-0 md:block md:w-72`}
        >
          <div className="p-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Tus chats ({sessions.length})
          </div>
          {sessionsQ.isLoading && (
            <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
            </div>
          )}
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`relative border-b ${s.id === sessionId ? "bg-muted" : ""}`}
            >
              <button
                onClick={() => openSession(s.id, s.project)}
                className="block w-full px-3 py-2 pr-9 text-left hover:bg-muted/50"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px] font-semibold text-primary">
                    {s.project}
                    {s.remote ? " · 📱" : ""}
                  </span>
                  <span className="shrink-0 text-[10px] text-muted-foreground">
                    {timeAgo(s.mtime)}
                  </span>
                </div>
                <div className="truncate text-xs">{s.title}</div>
                {s.last && (
                  <div className="truncate text-[11px] text-muted-foreground">
                    {s.last}
                  </div>
                )}
              </button>
              <button
                onClick={() => doRename(s)}
                className="absolute right-1 top-1.5 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                title="Renombrar"
                aria-label="renombrar"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </aside>

        {/* Hilo de chat */}
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex-1 space-y-3 overflow-y-auto p-3 sm:p-4">
            {messages.length === 0 && (
              <div className="mx-auto mt-10 max-w-sm text-center text-sm text-muted-foreground">
                <p className="font-medium">Chat de Claude sobre tus proyectos</p>
                <p className="mt-1 text-xs">
                  Proyecto: <b>{project || "—"}</b>. Escribe abajo o sube una
                  imagen/captura. Abre un chat anterior con el botón{" "}
                  <b>Chats</b>.
                </p>
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`flex ${
                  m.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3 py-2 text-sm ${
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  }`}
                >
                  {m.text || (streaming && i === messages.length - 1 ? "…" : "")}
                </div>
              </div>
            ))}
            {err && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
                {err}
              </div>
            )}
            {remoteMsg && (
              <div className="space-y-1 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-2 text-xs">
                <div>{remoteMsg}</div>
                {remoteUrl && (
                  <a
                    href={remoteUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-semibold text-emerald-600 underline dark:text-emerald-400"
                  >
                    <Smartphone className="h-3.5 w-3.5" /> Abrir en la app
                  </a>
                )}
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* Input */}
          <div className="border-t p-2 sm:p-3">
            {images.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {images.map((f, i) => (
                  <span
                    key={i}
                    className="flex items-center gap-1 rounded-full border bg-muted px-2 py-0.5 text-[11px]"
                  >
                    {f.name.slice(0, 18)}
                    <X
                      className="h-3 w-3 cursor-pointer"
                      onClick={() =>
                        setImages((im) => im.filter((_, j) => j !== i))
                      }
                    />
                  </span>
                ))}
              </div>
            )}
            <div className="flex items-end gap-2">
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(e) =>
                  setImages((im) => [...im, ...Array.from(e.target.files ?? [])])
                }
              />
              <Button
                variant="outline"
                size="icon"
                className="h-10 w-10 shrink-0"
                onClick={() => fileRef.current?.click()}
                disabled={streaming}
                aria-label="adjuntar imagen"
              >
                <ImagePlus className="h-4 w-4" />
              </Button>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                rows={1}
                placeholder="Escribe a Claude…"
                className="max-h-32 min-h-10 flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm"
              />
              <Button
                size="icon"
                className="h-10 w-10 shrink-0"
                onClick={send}
                disabled={streaming || (!input.trim() && images.length === 0)}
                aria-label="enviar"
              >
                {streaming ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
