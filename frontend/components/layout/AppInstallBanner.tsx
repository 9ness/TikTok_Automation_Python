"use client";

import { Download, X } from "lucide-react";
import { useEffect, useState } from "react";

import { enAlgunaApp, enLaApp } from "@/lib/entorno-app";

// Nuestro dominio, no el de GitHub: ver `app/apk/route.ts`. Yendo a GitHub la
// descarga se quedaba clavada en "Descargando…" dentro de la app.
const APK_URL = "/apk";
const OCULTO_KEY = "apk-banner-oculto";
const OCULTO_ACTUALIZAR_KEY = "apk-banner-actualizar-oculto";

/** Aviso de la APK, solo a quien le sirve. Tiene DOS casos.
 *
 *  1. **Actualizar** — se está en Android y NO en la APK nueva. Es el caso
 *     gordo mientras dure la migración: quien sigue en la TWA no tiene forma de
 *     enterarse de que hay una app nueva, porque el aviso de versión va DENTRO
 *     de la nueva.
 *
 *     Se detecta por descarte —Android sin `TTShopApp` en el User-Agent— y no
 *     por el referrer `android-app://`, que era lo suyo pero NO sirve: la TWA
 *     solo lo pone en la navegación de arranque, así que en cuanto se recarga o
 *     se navega, desaparece y el banner no salía nunca. Pasó en el móvil.
 *
 *  2. **Instalar** — igual pero sin señal de que haya ninguna app: se ofrece
 *     instalarla. Si ya está abierta desde el icono de la pantalla de inicio
 *     (`display-mode: standalone`) no se dice nada, que ahí es ruido.
 *
 *  Dentro de la APK nueva (`TTShopApp`) no sale nada: ella ya avisa sola.
 *
 *  El descarte del de instalar se recuerda para siempre (reaparecer en cada
 *  carga es peor que no ponerlo). El de actualizar solo hasta cerrar la app: es
 *  un salto de una vez y darle a la X no debería dejarte en la vieja para
 *  siempre.
 */
export function AppInstallBanner() {
  const [modo, setModo] = useState<"instalar" | "actualizar" | null>(null);

  useEffect(() => {
    const esAndroid = /android/i.test(navigator.userAgent);
    if (!esAndroid) return;

    if (enLaApp()) return;

    if (enAlgunaApp()) {
      if (sessionStorage.getItem(OCULTO_ACTUALIZAR_KEY) !== "1") setModo("actualizar");
      return;
    }

    // Ni app nueva ni señal de app vieja: o es el navegador, o es la TWA que ya
    // perdió el referrer. Mientras dure la migración se ofrece igual, porque
    // quedarse callado deja a quien está en la vieja sin enterarse.
    if (localStorage.getItem(OCULTO_KEY) !== "1") setModo("instalar");
  }, []);

  if (!modo) return null;

  const actualizar = modo === "actualizar";

  function cerrar() {
    if (actualizar) sessionStorage.setItem(OCULTO_ACTUALIZAR_KEY, "1");
    else localStorage.setItem(OCULTO_KEY, "1");
    setModo(null);
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-border/60 bg-card/95 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur md:hidden">
      <div className="mx-auto flex max-w-md items-center gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/icon-192.png" alt="" className="h-10 w-10 shrink-0 rounded-lg" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold">
            {actualizar ? "Hay una versión nueva" : "Instala la app"}
          </p>
          <p className="text-[11px] leading-tight text-muted-foreground">
            {actualizar
              ? "Se instala encima. Después habrá que meter el PIN otra vez."
              : "Descargas en su carpeta y subidas en segundo plano."}
          </p>
        </div>
        <a
          href={APK_URL}
          className="flex shrink-0 items-center gap-1 rounded-lg bg-cyan-500 px-3 py-2 text-[11px] font-semibold text-black transition hover:bg-cyan-400"
        >
          <Download className="h-3.5 w-3.5" /> {actualizar ? "Actualizar" : "APK"}
        </a>
        <button
          type="button"
          onClick={cerrar}
          aria-label="Cerrar aviso"
          className="shrink-0 rounded-md p-1 text-muted-foreground hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
