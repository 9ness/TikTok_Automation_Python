"use client";

import { Download, X } from "lucide-react";
import { useEffect, useState } from "react";

const APK_URL =
  "https://github.com/9ness/TikTok_Automation_Python/releases/download/apk-latest/tiktok-auto.apk";
const OCULTO_KEY = "apk-banner-oculto";

/** Aviso para bajarse la APK, solo a quien le sirve.
 *
 *  Se enseña únicamente en Android y SOLO si se está navegando por el
 *  navegador: si ya se abrió desde la APK o desde el icono de la pantalla de
 *  inicio, ofrecer "instala la app" es ruido. Esos dos casos se detectan
 *  distinto y hacen falta los dos:
 *    - instalada desde el navegador → `display-mode: standalone`
 *    - abierta desde la APK (TWA)   → el referrer es `android-app://`
 *
 *  El descarte se recuerda en localStorage: un aviso que reaparece en cada
 *  carga acaba siendo peor que no ponerlo.
 */
export function AppInstallBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(OCULTO_KEY) === "1") return;

    const esAndroid = /android/i.test(navigator.userAgent);
    const instalada =
      window.matchMedia("(display-mode: standalone)").matches ||
      // iOS lo expone aquí; se mira igualmente por si se añade soporte.
      (window.navigator as { standalone?: boolean }).standalone === true;
    const dentroDeLaApk = document.referrer.startsWith("android-app://");

    setVisible(esAndroid && !instalada && !dentroDeLaApk);
  }, []);

  if (!visible) return null;

  function cerrar() {
    localStorage.setItem(OCULTO_KEY, "1");
    setVisible(false);
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-border/60 bg-card/95 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur md:hidden">
      <div className="mx-auto flex max-w-md items-center gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/icon-192.png" alt="" className="h-10 w-10 shrink-0 rounded-lg" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold">Instala la app</p>
          <p className="text-[11px] leading-tight text-muted-foreground">
            Pantalla completa y con su icono. Se actualiza sola.
          </p>
        </div>
        <a
          href={APK_URL}
          className="flex shrink-0 items-center gap-1 rounded-lg bg-cyan-500 px-3 py-2 text-[11px] font-semibold text-black transition hover:bg-cyan-400"
        >
          <Download className="h-3.5 w-3.5" /> APK
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
