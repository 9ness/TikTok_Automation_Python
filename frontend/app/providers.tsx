"use client";

import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
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
import { useTheme } from "next-themes";
import { useMenuPrefs } from "@/lib/queries/uiMenu";
import { avisarModalAbierto, esAppNativa } from "@/lib/subidaNativa";

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

/** Aplica el tema guardado en la CUENTA (Redis), no solo en el dispositivo:
 *  así Ana lo tiene en claro en el móvil, en el PC y en la APK sin tocar nada
 *  en cada uno. Se aplica una vez por valor, para no pelear con el
 *  interruptor mientras alguien lo está cambiando. */
function TemaDelUsuario() {
  const prefs = useMenuPrefs();
  const { setTheme } = useTheme();
  const aplicado = useRef("");
  const tema = prefs.data?.tema ?? "";
  useEffect(() => {
    if (!tema || tema === aplicado.current) return;
    aplicado.current = tema;
    setTheme(tema);
  }, [tema, setTheme]);
  return null;
}

/** Marca el `<html>` cuando se está dentro de la app de Android.
 *
 *  De ahí cuelgan los ajustes de `globals.css` que hacen falta SOLO en el
 *  WebView: sin animación de entrada y sin desenfoque detrás de las ventanas
 *  emergentes (ver el comentario allí). */
function MarcaAppNativa() {
  useEffect(() => {
    if (esAppNativa()) document.documentElement.classList.add("app-nativa");
  }, []);
  return null;
}

/** Vigila si hay alguna ventana emergente abierta y se lo cuenta a la app.
 *
 *  Radix pinta los diálogos y la Cola como `[role="dialog"]` con
 *  `data-state="open"` colgados del `body`, así que basta con observar el
 *  `body`. Se avisa solo cuando cambia (abierto ↔ cerrado), no en cada
 *  mutación. */
function ModalesEnLaApp() {
  useEffect(() => {
    if (typeof document === "undefined") return;
    let ultimo = false;
    const mirar = () => {
      const abierto = Boolean(document.querySelector('[role="dialog"][data-state="open"]'));
      if (abierto !== ultimo) {
        ultimo = abierto;
        avisarModalAbierto(abierto);
      }
    };
    const obs = new MutationObserver(mirar);
    obs.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["data-state"],
    });
    mirar();
    return () => {
      obs.disconnect();
      if (ultimo) avisarModalAbierto(false);
    };
  }, []);
  return null;
}

/** Los avisos, en el tema que se esté viendo (antes iban fijos en oscuro). */
function ToasterConTema() {
  const { resolvedTheme } = useTheme();
  return (
    <Toaster
      richColors
      position="top-right"
      theme={resolvedTheme === "light" ? "light" : "dark"}
    />
  );
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
        <TemaDelUsuario />
        <MarcaAppNativa />
        <ModalesEnLaApp />
        <ToasterConTema />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
