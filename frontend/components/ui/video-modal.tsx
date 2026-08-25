"use client";

import { useEffect, useRef, useState } from "react";
import { Download, ExternalLink, Film, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Portal } from "@/components/ui/portal";

/** Volumen por defecto al abrir el modal (15%). El usuario puede subirlo
 *  en los controles del player si quiere. */
const DEFAULT_VOLUME = 0.15;

/**
 * Modal de vídeo TOTALMENTE custom (sin Radix Dialog) para garantizar
 * control absoluto del width. 320px fijo en desktop, full-width-minus-margin
 * en móvil. Usado por la cola (`JobVideoDialog`) y el histórico TikTok Shop
 * (`VideoPlayer`).
 */
export function VideoModal({
  open,
  onOpenChange,
  title,
  filename,
  videoUrl,
  downloadUrl,
  localPath,
  placeholderMessage,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  title: string;
  filename: string;
  videoUrl: string | null;
  downloadUrl: string | null;
  localPath?: string | null;
  placeholderMessage?: string;
}) {
  const driveSearchUrl = filename
    ? `https://drive.google.com/drive/search?q=${encodeURIComponent(filename)}`
    : null;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  // Velocidad de reproducción — para repasar vídeos más rápido (1x / 1.5x / 2x).
  const SPEEDS = [1, 1.5, 2] as const;
  const [speed, setSpeed] = useState<number>(1);

  function applySpeed(s: number) {
    setSpeed(s);
    const v = videoRef.current;
    if (v) v.playbackRate = s;
  }

  // Volumen por defecto al abrir. Se aplica en cuanto el video monta y
  // cada vez que se reabre — el atributo `volume` HTML no es respetado
  // por todos los browsers, hay que setearlo vía JS sobre el elemento.
  useEffect(() => {
    if (!open) return;
    const v = videoRef.current;
    if (v) {
      v.volume = DEFAULT_VOLUME;
      v.playbackRate = speed;
    }
  }, [open, videoUrl, speed]);

  // Cerrar con Escape
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onOpenChange(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  // Bloquear scroll del body cuando está abierto
  useEffect(() => {
    if (!open) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [open]);

  if (!open) return null;

  // Colgado del `<body>`: este modal se usa DENTRO del cajón de la cola, y ahí
  // no llegaba a abrirse.
  return (
    <Portal>
    <div
      role="dialog"
      aria-modal="true"
      onClick={() => onOpenChange(false)}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 50,
        backgroundColor: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1rem",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-card text-foreground border shadow-xl"
        style={{
          width: "320px",
          maxWidth: "calc(100vw - 2rem)",
          maxHeight: "calc(100vh - 2rem)",
          minHeight: "16rem",
          overflowY: "auto",
          borderRadius: "0.5rem",
          padding: "1rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.75rem",
        }}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-base font-semibold">{title}</h2>
            <p className="truncate font-mono text-xs text-muted-foreground">
              {filename}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Cerrar"
            className="rounded-sm p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Video */}
        {videoUrl ? (
          // `flexShrink: 0` es la clave: esto es un hijo flex dentro de una
          // caja con `maxHeight`, así que por defecto se encoge para caber. El
          // vídeo se queda en nada y el modal sale como una TIRA con solo el
          // título — que es exactamente lo que se veía en el móvil. Mismo
          // fallo que tuvo el visor de fotos.
          <div className="overflow-hidden rounded-md bg-black" style={{ flexShrink: 0 }}>
            <video
              ref={videoRef}
              src={videoUrl}
              controls
              preload="metadata"
              playsInline
              onLoadedMetadata={(e) => {
                // Defensa adicional por si el useEffect corre antes que el
                // metadata cargue (en algunos navegadores `volume`/`playbackRate`
                // antes de loadedmetadata no persisten).
                const el = e.currentTarget as HTMLVideoElement;
                el.volume = DEFAULT_VOLUME;
                el.playbackRate = speed;
              }}
              className="w-full"
              // El tope de alto es para que quepan debajo la velocidad y los
              // botones sin desplazarse dentro de la ventana: un 9/16 a 320 px
              // de ancho mide 569 px y en un móvil se comía la pantalla.
              // `objectFit: contain` para que el recorte no deforme el vídeo.
              style={{
                aspectRatio: "9 / 16",
                maxHeight: "55vh",
                objectFit: "contain",
                display: "block",
              }}
            />
            {/* Velocidad de reproducción — repasar más rápido */}
            <div className="flex items-center justify-center gap-1 bg-black/80 px-2 py-1.5">
              <span className="mr-1 text-[10px] text-white/60">Velocidad</span>
              {SPEEDS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => applySpeed(s)}
                  className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                    speed === s
                      ? "bg-white text-black"
                      : "bg-white/15 text-white hover:bg-white/25"
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div
            className="flex flex-col items-center justify-center gap-2 rounded-md border bg-muted text-muted-foreground"
            style={{ aspectRatio: "9 / 16", flexShrink: 0 }}
          >
            <Film className="h-8 w-8" />
            <p className="px-4 text-center text-sm">
              {placeholderMessage ?? "Sin vídeo disponible"}
            </p>
          </div>
        )}

        {/* Botones */}
        {downloadUrl && (
          <div className="grid grid-cols-2 gap-2">
            <Button asChild variant="outline" size="sm">
              <a href={downloadUrl} download={filename}>
                <Download className="h-4 w-4" />
                Descargar
              </a>
            </Button>
            {driveSearchUrl && (
              <Button asChild variant="outline" size="sm">
                <a href={driveSearchUrl} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="h-4 w-4" />
                  Drive
                </a>
              </Button>
            )}
          </div>
        )}

        {/* Path local */}
        {localPath && (
          <p
            className="break-all rounded bg-muted/40 p-2 text-[10px] font-mono text-muted-foreground"
            title={localPath}
          >
            {localPath}
          </p>
        )}
      </div>
    </div>
    </Portal>
  );
}
