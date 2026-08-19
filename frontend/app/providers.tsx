"use client";

import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Toaster } from "sonner";

import { QueueDrawer } from "@/components/queue/QueueDrawer";
import { QueueWebSocketBridge } from "@/components/queue/QueueWebSocketBridge";
import { asegurarDueno, esDeNicho, hidratar, vigilar } from "@/lib/cache-persistente";
import { useMe } from "@/lib/queries/auth";
import { ThemeProvider } from "@/lib/theme";

/** Rellena la caché con lo último que se vio, PERO solo cuando ya se sabe de
 *  quién es la sesión.
 *
 *  Al reabrir la app (Android la mata al rato de dejarla de fondo) la caché
 *  arranca vacía y toca esperar otra vez al Drive, que son segundos. Se pinta
 *  lo guardado y React Query refresca por detrás.
 *
 *  Lo de esperar a `/me` no es un detalle: los listados guardados llevan el
 *  progreso de una PERSONA (carpetas hechas, subidos, escaparate). Hidratando
 *  a ciegas, el admin entraba en la cuenta de Ana y veía pintado su propio
 *  progreso hasta que respondía el Drive. `/me` es una llamada local de unos
 *  milisegundos; el listado del Drive tarda segundos, así que lo que se gana
 *  en pintura rápida sigue estando.
 */
function CachePersistente() {
  const qc = useQueryClient();
  const usuario = useMe().data?.username ?? null;

  useEffect(() => {
    if (!usuario) return;
    if (asegurarDueno(usuario)) {
      // Era de otra persona: fuera también lo que ya hubiera en memoria (al
      // cambiar de cuenta sin recargar, o si la sesión cambia por su cuenta).
      qc.removeQueries({ predicate: (q) => esDeNicho(q.queryKey) });
    }
    hidratar(qc);
    return vigilar(qc);
  }, [qc, usuario]);

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
