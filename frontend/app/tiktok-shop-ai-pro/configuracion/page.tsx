"use client";

import { Settings } from "lucide-react";

import { EchoTikPanel, HashtagsPanel } from "@/components/tiktok-shop-ai-pro/PanelesConfig";
import { PanelBackup } from "@/components/tiktok-shop-ai-pro/PanelBackup";
import { PanelCarruseles } from "@/components/tiktok-shop-ai-pro/PanelCarruseles";
import { PanelGuiones } from "@/components/tiktok-shop-ai-pro/PanelGuiones";
import { PanelTextos } from "@/components/tiktok-shop-ai-pro/PanelTextos";
import { PanelUrls } from "@/components/tiktok-shop-ai-pro/PanelUrls";

/** EchoTik apagado a petición del operador (su cuota gratis no da para el
 *  volumen diario). Poniéndolo a `true` vuelve el panel de credenciales. */
const MOSTRAR_ECHOTIK = false;

/** Ajustes de Tiktok Shop AI Pro, fuera de las pantallas de trabajo.
 *
 *  Estaban plegados DENTRO de cada nicho y aun así estorbaban: son cosas que se
 *  tocan de uvas a peras (los hashtags al cambiar de campaña, la copia si
 *  sospechas que han borrado algo) y lo de todos los días es la carpeta de
 *  productos. Aquí valen para todos los nichos a la vez, que además es la
 *  verdad: los hashtags y la copia son únicos.
 */
export default function ConfiguracionAiProPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-3 p-3 sm:p-4">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-lg font-semibold sm:text-xl">
          <Settings className="h-5 w-5 text-muted-foreground" /> Configuración
        </h1>
        <p className="text-[11px] text-muted-foreground sm:text-xs">
          Hashtags del caption, textos y guiones de todo un catálogo, y copia
          de seguridad del Drive del curso. Lo de aquí vale para todos los
          nichos: no hay que repetirlo en cada uno.
        </p>
      </header>

      <HashtagsPanel />
      <PanelUrls />
      <PanelTextos />
      <PanelGuiones />
      <PanelCarruseles />
      <PanelBackup />
      {MOSTRAR_ECHOTIK && <EchoTikPanel />}
    </div>
  );
}
