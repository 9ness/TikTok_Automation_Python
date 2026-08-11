"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Toaster } from "sonner";

import { QueueDrawer } from "@/components/queue/QueueDrawer";
import { QueueWebSocketBridge } from "@/components/queue/QueueWebSocketBridge";
import { hidratar, vigilar } from "@/lib/cache-persistente";
import { ThemeProvider } from "@/lib/theme";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  // Al reabrir la app (Android la mata al rato de dejarla de fondo) la caché
  // arranca vacía y toca esperar otra vez al Drive. Se rellena con lo último
  // que se vio para que la pantalla salga pintada, y React Query refresca por
  // detrás. Va en un efecto: `localStorage` no existe en el servidor.
  useEffect(() => {
    hidratar(client);
    return vigilar(client);
  }, [client]);

  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <QueueWebSocketBridge />
        {children}
        <QueueDrawer />
        <Toaster richColors position="top-right" theme="dark" />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
