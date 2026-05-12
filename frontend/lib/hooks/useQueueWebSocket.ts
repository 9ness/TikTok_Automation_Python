"use client";

import { useEffect, useRef } from "react";

import { api } from "@/lib/api";
import { useQueueStore } from "@/lib/stores/queueStore";
import type { WsEvent } from "@/lib/types/queue";

const PING_INTERVAL_MS = 30_000;
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

function buildWsUrl(): string {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const base = `${api.wsUrl}/ws/queue`;
  return apiKey ? `${base}?api_key=${encodeURIComponent(apiKey)}` : base;
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
  const setSnapshot = useQueueStore((s) => s.setSnapshot);
  const upsertJobs = useQueueStore((s) => s.upsertJobs);
  const applyProgress = useQueueStore((s) => s.applyProgress);
  const removeJobs = useQueueStore((s) => s.removeJobs);
  const setConnection = useQueueStore((s) => s.setConnection);

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
        ws = new WebSocket(buildWsUrl());
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

    return () => {
      stoppedRef.current = true;
      clearTimers();
      const ws = wsRef.current;
      if (ws && ws.readyState !== WebSocket.CLOSED) {
        ws.close();
      }
      wsRef.current = null;
    };
  }, [setSnapshot, upsertJobs, applyProgress, removeJobs, setConnection]);
}
