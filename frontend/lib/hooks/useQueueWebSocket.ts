"use client";

import { useEffect, useRef } from "react";

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
 * llamadas crean conexiones extra; usa `QueueWebSocketProvider`.
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

  const wsRef = useRef<WebSocket | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const stoppedRef = useRef(false);

  useEffect(() => {
    stoppedRef.current = false;

    function clearTimers() {
      if (pingTimerRef.current) {
        clearInterval(pingTimerRef.current);
        pingTimerRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    }

    function scheduleReconnect() {
      if (stoppedRef.current) return;
      const delay = Math.min(
        RECONNECT_BASE_MS * 2 ** attemptRef.current,
        RECONNECT_MAX_MS,
      );
      attemptRef.current += 1;
      reconnectTimerRef.current = setTimeout(connect, delay);
    }

    function connect() {
      if (stoppedRef.current) return;
      setConnection("connecting");
      let ws: WebSocket;
      try {
        ws = new WebSocket(buildWsUrl(verDe));
      } catch (e) {
        setConnection("disconnected", e instanceof Error ? e.message : "WS error");
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setConnection("connected");
        // Iniciar pings periódicos
        pingTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, PING_INTERVAL_MS);
      };

      ws.onmessage = (ev) => {
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
        setConnection("disconnected", "ws_error");
      };

      ws.onclose = () => {
        if (pingTimerRef.current) {
          clearInterval(pingTimerRef.current);
          pingTimerRef.current = null;
        }
        wsRef.current = null;
        if (!stoppedRef.current) {
          setConnection("disconnected");
          scheduleReconnect();
        }
      };
    }

    connect();

    // Con la app de fondo no hay nadie mirando la cola, pero el socket seguía
    // abierto haciendo ping cada pocos segundos: gasta batería y mantiene
    // trabajo vivo en un proceso que Android ya está mirando con lupa para
    // matarlo (es lo que dice el chivato que pasa). Se suelta al minuto de
    // esconderse y se vuelve a conectar al volver — el servidor manda un
    // `snapshot` al reconectar, así que no se pierde ningún job.
    let dormir: ReturnType<typeof setTimeout> | null = null;

    function alCambiarVisibilidad() {
      if (document.visibilityState === "hidden") {
        dormir = setTimeout(() => {
          stoppedRef.current = true;
          clearTimers();
          const ws = wsRef.current;
          if (ws && ws.readyState !== WebSocket.CLOSED) ws.close();
          wsRef.current = null;
          setConnection("disconnected");
        }, HIDDEN_CLOSE_MS);
        return;
      }
      if (dormir) {
        clearTimeout(dormir);
        dormir = null;
      }
      // Al volver: si se había soltado, reconectar de inmediato.
      if (!wsRef.current) {
        stoppedRef.current = false;
        attemptRef.current = 0;
        connect();
      }
    }

    document.addEventListener("visibilitychange", alCambiarVisibilidad);

    return () => {
      stoppedRef.current = true;
      if (dormir) clearTimeout(dormir);
      document.removeEventListener("visibilitychange", alCambiarVisibilidad);
      clearTimers();
      const ws = wsRef.current;
      if (ws && ws.readyState !== WebSocket.CLOSED) {
        ws.close();
      }
      wsRef.current = null;
    };
  }, [setSnapshot, upsertJobs, applyProgress, removeJobs, setConnection]);
}
