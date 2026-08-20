"use client";

import type { Route } from "next";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { enAlgunaApp } from "@/lib/entorno-app";

const CLAVE = "ultima-pantalla";
/** Más allá de esto se entiende que es una sesión nueva y se entra al
 *  dashboard, que es lo que uno espera al abrir la app por la mañana. */
const FRESCURA_MS = 6 * 60 * 60 * 1000;

/** Devuelve a la pantalla donde estabas cuando Android mata la app.
 *
 *  Android reinicia la tarea cuando la app lleva un rato en segundo plano o
 *  hace falta memoria. Eso no se puede evitar desde la web, pero sí se puede
 *  hacer que no duela: al arrancar de cero, si estabas en otra pantalla hace
 *  poco, se vuelve a ella.
 *
 *  Solo actúa con la app INSTALADA (o la APK) — ver `lib/entorno-app.ts`, que
 *  es donde está la parte delicada de saberlo. En el navegador normal abrir una
 *  pestaña en "/" y que te mande a otro sitio sería un secuestro molesto —ahí
 *  hay pestañas e historial, y el problema del reinicio no existe.
 *
 *  Solo actúa además en la carga inicial: dentro de la app la navegación es del
 *  cliente y no vuelve a montar esto, así que pulsar "inicio" te deja en
 *  inicio, como debe ser.
 */
export function RestaurarPantalla() {
  const pathname = usePathname();
  const router = useRouter();
  const yaMirado = useRef(false);

  useEffect(() => {
    if (yaMirado.current) return;
    yaMirado.current = true;
    if (pathname !== "/" || !enAlgunaApp()) return;

    try {
      const crudo = localStorage.getItem(CLAVE);
      if (!crudo) return;
      const { path, ts } = JSON.parse(crudo) as { path: string; ts: number };
      if (path && path !== "/" && Date.now() - ts < FRESCURA_MS) {
        // `typedRoutes` quiere una ruta conocida en compilación; esta sale
        // de localStorage, así que no hay forma de comprobarla antes.
        router.replace(path as Route);
      }
    } catch {
      // localStorage lleno o JSON corrupto: no es motivo para romper el arranque.
    }
  }, [pathname, router]);

  // Se apunta en cada cambio de pantalla, no al cerrar: cuando Android mata la
  // app no hay ningún evento fiable de despedida — `beforeunload` no llega.
  useEffect(() => {
    try {
      localStorage.setItem(CLAVE, JSON.stringify({ path: pathname, ts: Date.now() }));
    } catch {
      /* idem */
    }
  }, [pathname]);

  return null;
}
