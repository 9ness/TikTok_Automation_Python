"use client";

import { useEffect } from "react";

import { api } from "@/lib/api";
import { useQueueStore } from "@/lib/stores/queueStore";
import type { WsEvent } from "@/lib/types/queue";

const PING_INTERVAL_MS = 30_000;
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;
/** Cuánto se espera con la app escondida antes de soltar el socket. Un minuto
 *  para no cortar por mirar una notificación y volver. */
const HIDDEN_CLOSE_MS = 60_000;

function buildWsUrl(de: string): string {
  const params = new URLSearchParams();
  const apiK = process.env.NEXT_PUBLIC_API_KEY;
  if (apiK) params.set("api_key", apiK);
  // `de` solo lo respeta el backend si quien mira es admin.
  if (de) params.set("de", de);
  const qs = params.toString();
  return qs ? `${api.wsUrl}/ws/queue?${qs}` : `${api.wsUrl}/ws/queue`;
}

/**
 * Conecta al `/ws/queue` y propaga eventos al `useQueueStore`.
 *
 * - Reconexión exponencial 1s → 2s → 4s → 8s → 16s → 30s (cap).
 * - Ping cada 30s para keep-alive (servidor responde con pong).
 * - Al reconectar, el servidor envía `snapshot` automáticamente — el store
 *   se reescribe completo, no quedan jobs huérfanos.
 *
 * Diseñado para invocarse UNA VEZ desde un provider de raíz. Múltiples
 * llamadas crean conexiones extra; usa `QueueWebSocketBridge`.
 *
 * TODO el estado del socket vive DENTRO del efecto, no en `useRef`. Con refs
 * compartidas entre ejecuciones pasaba esto al cambiar de cola con el selector
 * "Viendo": el cierre del socket viejo es asíncrono y llegaba cuando el nuevo
 * ya estaba abierto, así que su `onclose` ponía a `null` la referencia del
 * NUEVO y programaba una reconexión con el filtro ANTERIOR (el que tenía
 * atrapado en su clausura). Acababas con dos sockets vivos mandando snapshots
 * contradictorios: se veía un par de recargas y ganaba el que contestara el
 * último, casi siempre el viejo. Con variables locales, cada ejecución del
 * efecto tiene lo suyo y la anterior no puede tocar nada.
 */
export function useQueueWebSocket(): void {
  // De quién ver la cola. Solo lo respeta el backend si eres admin; al
  // cambiarlo se reconecta el socket con el filtro nuevo.
  const verDe = useQueueStore((s) => s.verDe);
  const setSnapshot = useQueueStore((s) => s.setSnapshot);
  const upsertJobs = useQueueStore((s) => s.upsertJobs);
  const applyProgress = useQueueStore((s) => s.applyProgress);
  const removeJobs = useQueueStore((s) => s.removeJobs);
  const setConnection = useQueueStore((s) => s.setConnection);
  const setViendo = useQueueStore((s) => s.setViendo);
  const setOtros = useQueueStore((s) => s.setOtros);

  useEffect(() => {
    /** ¿Sigue mandando esta ejecución del efecto? Al cambiar `verDe` (o al
     *  desmontar) pasa a `false` y todo lo que quede en vuelo se ignora. */
    let vivo = true;
    /** Soltado a propósito por tener la app de fondo (no es un corte). */
    let dormido = false;
    let socket: WebSocket | null = null;
    let pingTimer: ReturnType<typeof setInterval> | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let dormirTimer: ReturnType<typeof setTimeout> | null = null;
    let intentos = 0;

    function pararTimers() {
      if (pingTimer) {
        clearInterval(pingTimer);
        pingTimer = null;
      }
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    }

    function reconectarLuego() {
      if (!vivo || dormido) return;
      const espera = Math.min(RECONNECT_BASE_MS * 2 ** intentos, RECONNECT_MAX_MS);
      intentos += 1;
      reconnectTimer = setTimeout(conectar, espera);
    }

    function conectar() {
      if (!vivo || dormido) return;
      setConnection("connecting");
      let ws: WebSocket;
      try {
        ws = new WebSocket(buildWsUrl(verDe));
      } catch (e) {
        setConnection("disconnected", e instanceof Error ? e.message : "WS error");
        reconectarLuego();
        return;
      }
      socket = ws;

      /** ¿Este socket sigue siendo el bueno? Un socket viejo puede seguir
       *  emitiendo eventos un rato después de haberlo sustituido. */
      const actual = () => vivo && socket === ws;

      ws.onopen = () => {
        if (!actual()) return;
        intentos = 0;
        setConnection("connected");
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, PING_INTERVAL_MS);
      };

      ws.onmessage = (ev) => {
        if (!actual()) return;
        let payload: WsEvent;
        try {
          payload = JSON.parse(ev.data);
        } catch {
          return;
        }
        switch (payload.type) {
          case "snapshot":
            setSnapshot(payload.data.jobs);
            setViendo(payload.data.viendo ?? "", payload.data.es_admin ?? false);
            setOtros(payload.data.otros ?? {});
            break;
          case "otros":
            setOtros(payload.data.otros ?? {});
            break;
          case "update":
            upsertJobs(payload.data.jobs);
            break;
          case "progress":
            applyProgress(payload.data.jobs);
            break;
          case "removed":
            removeJobs(payload.data.job_ids);
            break;
          case "pong":
            // No-op
            break;
        }
      };

      ws.onerror = () => {
        if (!actual()) return;
        setConnection("disconnected", "ws_error");
      };

      ws.onclose = () => {
        // Si este socket ya no es el vigente, no se toca NADA: ni la conexión
        // que se ve, ni la reconexión. Es el socket de la cola anterior
        // despidiéndose.
        if (!actual()) return;
        if (pingTimer) {
          clearInterval(pingTimer);
          pingTimer = null;
        }
        socket = null;
        if (dormido) return;
        setConnection("disconnected");
        reconectarLuego();
      };
    }

    conectar();

    // Con la app de fondo no hay nadie mirando la cola, pero el socket seguía
    // abierto haciendo ping cada pocos segundos: gasta batería y mantiene
    // trabajo vivo en un proceso que Android ya está mirando con lupa para
    // matarlo (es lo que dice el chivato que pasa). Se suelta al minuto de
    // esconderse y se vuelve a conectar al volver — el servidor manda un
    // `snapshot` al reconectar, así que no se pierde ningún job.
    function alCambiarVisibilidad() {
      if (document.visibilityState === "hidden") {
        dormirTimer = setTimeout(() => {
          dormido = true;
          pararTimers();
          const ws = socket;
          socket = null;
          if (ws && ws.readyState !== WebSocket.CLOSED) ws.close();
          setConnection("disconnected");
        }, HIDDEN_CLOSE_MS);
        return;
      }
      if (dormirTimer) {
        clearTimeout(dormirTimer);
        dormirTimer = null;
      }
      // Al volver: si se había soltado, reconectar de inmediato.
      if (!socket) {
        dormido = false;
        intentos = 0;
        conectar();
      }
    }

    document.addEventListener("visibilitychange", alCambiarVisibilidad);

    return () => {
      vivo = false;
      if (dormirTimer) clearTimeout(dormirTimer);
      document.removeEventListener("visibilitychange", alCambiarVisibilidad);
      pararTimers();
      const ws = socket;
      socket = null;
      if (ws && ws.readyState !== WebSocket.CLOSED) ws.close();
    };
  }, [
    verDe,
    setSnapshot,
    upsertJobs,
    applyProgress,
    removeJobs,
    setConnection,
    setViendo,
    setOtros,
  ]);
}
