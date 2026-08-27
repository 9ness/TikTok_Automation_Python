"use client";

import { useEffect, useRef } from "react";

/** Llama a `fn` cuando la app vuelve a primer plano.
 *
 *  `useAlTerminarJob` solo se entera de los trabajos que terminan con la
 *  pantalla abierta: los que ya estaban acabados al montar no disparan nada, a
 *  propósito (si no, entrar en una pantalla recargaría todo por trabajos de
 *  ayer). El agujero es el caso normal de trabajo: lanzas los guiones, sales de
 *  la app y vuelves cuando ya han terminado — y la lista sigue diciendo 0/6
 *  aunque el servidor los tenga escritos.
 *
 *  En la APP pasa siempre, porque volver de segundo plano no dispara el
 *  `focus` que React Query usa para revalidar.
 */
export function useRefrescarAlVolver(fn: () => void): void {
  const cb = useRef(fn);
  cb.current = fn;

  useEffect(() => {
    const alVolver = () => {
      if (document.visibilityState === "visible") cb.current();
    };
    document.addEventListener("visibilitychange", alVolver);
    return () => document.removeEventListener("visibilitychange", alVolver);
  }, []);
}
