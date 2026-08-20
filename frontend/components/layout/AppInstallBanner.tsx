"use client";

import { Download, X } from "lucide-react";
import { useEffect, useState } from "react";

const APK_URL =
  "https://github.com/9ness/TikTok_Automation_Python/releases/download/apk-latest/tiktok-auto.apk";
const OCULTO_KEY = "apk-banner-oculto";
const OCULTO_ACTUALIZAR_KEY = "apk-banner-actualizar-oculto";

/** Aviso de la APK, solo a quien le sirve. Tiene DOS casos.
 *
 *  1. **Instalar** — se navega desde el navegador de Android. Si ya se abrió
 *     desde la APK o desde el icono de la pantalla de inicio, ofrecer "instala
 *     la app" es ruido. Se detecta con `display-mode: standalone` (icono) y con
 *     `TTShopApp` en el User-Agent (la APK, que es un WebView y no cumple lo
 *     anterior; sin esto el banner salía DENTRO de la propia app).
 *
 *  2. **Actualizar** — se abre desde la APK VIEJA, la TWA. Se reconoce porque
 *     el referrer es `android-app://` pero el User-Agent no lleva `TTShopApp`.
 *     Hace falta porque la TWA no tiene forma de avisarse a sí misma: el aviso
 *     de versión nueva va dentro de la app nueva. Sin esto, quien no lea el
 *     mensaje se queda para siempre en la vieja, sin carpeta de descargas ni
 *     subida en segundo plano.
 *
 *  El descarte del de instalar se recuerda para siempre (reaparecer en cada
 *  carga es peor que no ponerlo). El de actualizar solo hasta cerrar: es un
 *  salto de una vez y darle a la X no debería dejarte en la vieja para siempre.
 */
export function AppInstallBanner() {
  const [modo, setModo] = useState<"instalar" | "actualizar" | null>(null);

  useEffect(() => {
    const esAndroid = /android/i.test(navigator.userAgent);
    if (!esAndroid) return;

    const enLaAppNueva = /TTShopApp/.test(navigator.userAgent);
    if (enLaAppNueva) return;

    if (document.referrer.startsWith("android-app://")) {
      if (sessionStorage.getItem(OCULTO_ACTUALIZAR_KEY) !== "1") setModo("actualizar");
      return;
    }

    const instalada =
      window.matchMedia("(display-mode: standalone)").matches ||
      // iOS lo expone aquí; se mira igualmente por si se añade soporte.
      (window.navigator as { standalone?: boolean }).standalone === true;
    if (instalada) return;

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
              : "Pantalla completa y con su icono. Se actualiza sola."}
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
