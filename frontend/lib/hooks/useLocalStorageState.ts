"use client";

import { useEffect, useState } from "react";

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * useState + persistencia automática en localStorage.
 *
 * - Lee el valor inicial del storage en el primer render del cliente
 *   (durante SSR usa siempre `defaultValue` para no romper la hidratación).
 * - Guarda cualquier cambio posterior.
 * - Si el JSON guardado está corrupto, cae a `defaultValue`.
 * - Si tanto el valor guardado como el default son objetos planos, fusiona
 *   `{ ...default, ...guardado }` para que un localStorage de una versión
 *   anterior (sin campos añadidos después) no deje propiedades `undefined`
 *   que revienten al hacer `.toFixed()`/`.map()` en el render.
 *
 * Nota: el valor inicial del SSR siempre es `defaultValue`. La sincronización
 * con storage ocurre en un `useEffect` post-mount, por lo que en componentes
 * que dependan de este valor para render pueden ver un "flash" del default
 * antes del valor real. Para el panel de config del nicho Presidentes ese
 * flash es invisible (el usuario no nota la diferencia entre defaults).
 */
export function useLocalStorageState<T>(
  key: string,
  defaultValue: T,
): [T, (next: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(defaultValue);

  // Cargar desde storage en mount (cliente only).
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(key);
      if (raw !== null) {
        const parsed = JSON.parse(raw) as T;
        // Fusiona sobre el default para rellenar campos añadidos después de
        // que el usuario guardara su config (si no, quedan `undefined`).
        setValue(
          isPlainObject(parsed) && isPlainObject(defaultValue)
            ? ({ ...defaultValue, ...parsed } as T)
            : parsed,
        );
      }
    } catch {
      // JSON corrupto — ignorar y mantener default.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // Guardar cualquier cambio.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // QuotaExceeded o storage deshabilitado — fallar en silencio.
    }
  }, [key, value]);

  return [value, setValue];
}
