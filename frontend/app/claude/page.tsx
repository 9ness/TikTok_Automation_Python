"use client";

import {
  ImagePlus,
  Loader2,
  MessageSquarePlus,
  PanelLeft,
  Pencil,
  Pin,
  PinOff,
  Rocket,
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
  startAllRemote,
  startRemote,
  stopRemote,
  streamChat,
  toggleAlwaysOn,
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
  // Lista filtrada según los tabs "Todos / 📌 Anclados / 📱 Remotos".
  // La barra superior sticky muestra los contadores y permite alternar.
  const filteredSessions = sessions.filter((s) => {
    if (filter === "pinned") return Boolean(s.always_on);
    if (filter === "remote") return Boolean(s.remote);
    return true;
  });

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
  const [startingAll, setStartingAll] = useState(false);
  const [pinningId, setPinningId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "pinned" | "remote">("all");

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
      let r = await startRemote(sessionId, project);
      // Solo hay 1 slot remoto. Si está ocupado por OTRA sesión (posible
      // remoto colgado), la liberamos y reintentamos una vez.
      if (!r.remote) {
        const busy = sessions.filter((s) => s.remote && s.id !== sessionId);
        for (const s of busy) {
          try {
            await stopRemote(s.id);
          } catch {
            /* best-effort */
          }
        }
        if (busy.length) r = await startRemote(sessionId, project);
      }
      setRemoteUrl(r.url ?? null);
      setRemoteMsg(
        r.remote
          ? "✅ Activado en la app. Abre este chat en el móvil:"
          : "⚠️ No se pudo activar el control remoto. Pulsa 📱✕ en el chat que lo tenga activo para liberarlo y reinténtalo.",
      );
      sessionsQ.refetch();
    } catch {
      setRemoteMsg("⚠️ Error activando el control remoto.");
    } finally {
      setRemoting(false);
    }
  }

  async function doStopRemote(s: ChatSession) {
    try {
      await stopRemote(s.id);
      setRemoteMsg("✅ Remoto liberado.");
      setRemoteUrl(null);
      sessionsQ.refetch();
    } catch {
      setErr("No se pudo desactivar el remoto.");
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
          {/* Barra superior sticky — siempre visible aunque scrolleés la lista */}
          <div className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
            <div className="flex items-center justify-between gap-2 p-2">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Tus chats ({filteredSessions.length}/{sessions.length})
              </div>
              <Button
                variant="outline"
                size="sm"
                className="h-7 gap-1 px-2 text-[11px]"
                disabled={startingAll}
                onClick={async () => {
                  setStartingAll(true);
                  setRemoteMsg(null);
                  try {
                    const r = await startAllRemote();
                    setRemoteMsg(
                      `Activados ${r.started} · ya activos ${r.already_active} · fallidos ${r.failed}`,
                    );
                    await sessionsQ.refetch();
                  } catch (e) {
                    setRemoteMsg(
                      `Error activando todos: ${(e as Error).message}`,
                    );
                  } finally {
                    setStartingAll(false);
                  }
                }}
                title="Activa Remote Control en todos los chats marcados 📌 (o los 10 más recientes si no hay pins). Tarda ~30-40s."
                aria-label="activar todos"
              >
                {startingAll ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Rocket className="h-3 w-3" />
                )}
                <span className="hidden sm:inline">Activar todos</span>
                <span className="sm:hidden">Todos</span>
              </Button>
            </div>
            {/* Tabs de filtro */}
            <div className="flex gap-1 px-2 pb-2">
              {(
                [
                  { key: "all", label: "Todos", icon: null, count: sessions.length },
                  {
                    key: "pinned",
                    label: "📌 Anclados",
                    icon: null,
                    count: sessions.filter((s) => s.always_on).length,
                  },
                  {
                    key: "remote",
                    label: "📱 Remotos",
                    icon: null,
                    count: sessions.filter((s) => s.remote).length,
                  },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setFilter(tab.key)}
                  className={`flex-1 rounded px-1.5 py-1 text-[10px] font-medium transition-colors ${
                    filter === tab.key
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted/50 text-muted-foreground hover:bg-muted"
                  }`}
                >
                  {tab.label}
                  <span className="ml-1 opacity-70">({tab.count})</span>
                </button>
              ))}
            </div>
          </div>
          {sessionsQ.isLoading && (
            <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
            </div>
          )}
          {filteredSessions.length === 0 && !sessionsQ.isLoading && (
            <div className="p-4 text-center text-[11px] text-muted-foreground">
              {filter === "pinned" && "Sin chats anclados aún. Ancla los que uses a menudo con 📌."}
              {filter === "remote" && "Ningún chat con Remote Control activo. Pulsa 🚀 Activar todos o abre uno."}
              {filter === "all" && "Sin chats."}
            </div>
          )}
          {filteredSessions.map((s) => (
            <div
              key={s.id}
              className={`relative border-b ${s.id === sessionId ? "bg-muted" : ""}`}
            >
              <button
                onClick={() => openSession(s.id, s.project)}
                className={`block w-full px-3 py-2 text-left hover:bg-muted/50 ${
                  s.remote ? "pr-24" : "pr-16"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px] font-semibold text-primary">
                    {s.project}
                    {s.always_on ? " · 📌" : ""}
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
              <button
                onClick={async () => {
                  setPinningId(s.id);
                  try {
                    await toggleAlwaysOn(s.id, !s.always_on);
                    await sessionsQ.refetch();
                  } catch (e) {
                    setRemoteMsg(`Error pin: ${(e as Error).message}`);
                  } finally {
                    setPinningId(null);
                  }
                }}
                className={`absolute right-8 top-1.5 rounded p-1 ${
                  s.always_on
                    ? "text-amber-500 hover:bg-muted hover:text-amber-600"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
                title={
                  s.always_on
                    ? "Quitar de la lista de arranque automático"
                    : "Añadir a arranque automático (se activa Remote Control al reiniciar el server)"
                }
                aria-label="pin arranque"
                disabled={pinningId === s.id}
              >
                {pinningId === s.id ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : s.always_on ? (
                  <Pin className="h-3.5 w-3.5" />
                ) : (
                  <PinOff className="h-3.5 w-3.5" />
                )}
              </button>
              {s.remote && (
                <button
                  onClick={() => doStopRemote(s)}
                  className="absolute right-16 top-1.5 rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
                  title="Desactivar control remoto (liberar slot)"
                  aria-label="desactivar remoto"
                >
                  <Smartphone className="h-3.5 w-3.5" />
                </button>
              )}
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
