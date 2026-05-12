"use client";

import { useQueueWebSocket } from "@/lib/hooks/useQueueWebSocket";

/**
 * Componente sin render que monta el WebSocket de la cola al cargar la app.
 * Va dentro de Providers, después de QueryClient. Renderiza null.
 */
export function QueueWebSocketBridge() {
  useQueueWebSocket();
  return null;
}
