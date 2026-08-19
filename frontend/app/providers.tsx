"use client";

import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Toaster } from "sonner";

import { QueueDrawer } from "@/components/queue/QueueDrawer";
import { QueueWebSocketBridge } from "@/components/queue/QueueWebSocketBridge";
import {
  esDeNicho,
  fijarUsuario,
  hidratar,
  ultimoUsuario,
  vigilar,
} from "@/lib/cache-persistente";
import { useMe } from "@/lib/queries/auth";
import { ThemeProvider } from "@/lib/theme";

/** Rellena la caché con lo último que vio ESTA persona.
 *
 *  Al reabrir la app (Android la mata al rato de dejarla de fondo) la caché
 *  arranca vacía y toca esperar otra vez al Drive, que son segundos. Se pinta
 *  lo guardado y React Query refresca por detrás.
 *
 *  Se hidrata YA, sin esperar a `/me`, con quien entró el último
 *  (`ultimoUsuario`): así no se pierde nada de velocidad. Y como cada persona
 *  tiene su propio cajón, lo que se pinta es lo suyo — antes, con un cajón
 *  único, el admin entraba en la cuenta de Ana y veía su propio progreso hasta
 *  que respondía el Drive.
 *
 *  Cuando `/me` contesta se comprueba: si resulta ser otra persona (sesión
 *  caducada, cambio desde otro sitio), se tira lo pintado y se hidrata del
 *  cajón bueno. Por el camino normal no pasa: quien cambia de cuenta deja
 *  escrito quién entra antes de recargar.
 */
function CachePersistente() {
  const qc = useQueryClient();
  const real = useMe().data?.username ?? null;
  // El de la primera pintura. `useState` con inicializador: se calcula una
  // sola vez y ANTES del primer efecto.
  const [ultimo] = useState(() =>
    typeof window === "undefined" ? "" : ultimoUsuario(),
  );
  const usuario = real ?? ultimo;

  useEffect(() => {
    if (!usuario) return;
    if (real && real !== ultimo) {
      // Lo hidratado era de otra persona: fuera de memoria antes de nada.
      qc.removeQueries({ predicate: (q) => esDeNicho(q.queryKey) });
      fijarUsuario(real);
    }
    hidratar(qc, usuario);
    return vigilar(qc, usuario);
  }, [qc, usuario, real, ultimo]);

  return null;
}

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

  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <CachePersistente />
        <QueueWebSocketBridge />
        {children}
        <QueueDrawer />
        <Toaster richColors position="top-right" theme="dark" />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
