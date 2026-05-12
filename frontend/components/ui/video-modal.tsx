"use client";

import { useEffect } from "react";
import { Download, ExternalLink, Film, X } from "lucide-react";

import { Button } from "@/components/ui/button";

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

  return (
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
          <div className="overflow-hidden rounded-md bg-black">
            <video
              src={videoUrl}
              controls
              preload="metadata"
              playsInline
              className="w-full"
              style={{ aspectRatio: "9 / 16", display: "block" }}
            />
          </div>
        ) : (
          <div
            className="flex flex-col items-center justify-center gap-2 rounded-md border bg-muted text-muted-foreground"
            style={{ aspectRatio: "9 / 16" }}
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
  );
}
