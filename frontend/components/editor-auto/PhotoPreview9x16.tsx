"use client";

import { Eye, EyeOff, ImageIcon } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";

/**
 * Previsualización 9:16 estilo TikTok para el tool `photo_insert`.
 *
 * La foto real se busca y descarga en runtime (famoso/marca detectado por
 * Gemini), así que aquí mostramos un PLACEHOLDER (recuadro con icono) en la
 * posición/tamaño configurados. Permite:
 *   - Click/drag dentro del frame → reposiciona el CENTRO de la foto.
 *   - Drag de la esquina inferior-derecha → cambia el tamaño en vivo.
 *
 * Mismas safe-zones que `SubsPreview9x16` / `StickerPreview9x16`.
 */

export interface PhotoPreviewConfig {
  position_x_pct: number;
  position_y_pct: number;
  scale_width_pct: number;
}

export function PhotoPreview9x16({
  config,
  onPositionChange,
  onScaleChange,
  className,
}: {
  config: PhotoPreviewConfig;
  onPositionChange?: (xPct: number, yPct: number) => void;
  onScaleChange?: (scalePct: number) => void;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dragKind = useRef<"move" | "resize" | null>(null);
  const resizeStart = useRef<{
    cx: number;
    cy: number;
    x: number;
    y: number;
    scale: number;
  } | null>(null);
  const [showSafeZones, setShowSafeZones] = useState(true);

  const updatePos = (clientX: number, clientY: number) => {
    if (!onPositionChange || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const xPct = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
    const yPct = Math.max(0, Math.min(100, ((clientY - rect.top) / rect.height) * 100));
    onPositionChange(Math.round(xPct), Math.round(yPct));
  };

  function handlePointerDown(e: React.PointerEvent) {
    if (!onPositionChange) return;
    dragKind.current = "move";
    (e.target as Element).setPointerCapture(e.pointerId);
    updatePos(e.clientX, e.clientY);
  }
  function handlePointerMove(e: React.PointerEvent) {
    if (dragKind.current === "move") {
      updatePos(e.clientX, e.clientY);
    } else if (dragKind.current === "resize" && resizeStart.current) {
      const { cx, cy, x, y, scale } = resizeStart.current;
      const distStart = Math.hypot(x - cx, y - cy) || 1;
      const distNow = Math.hypot(e.clientX - cx, e.clientY - cy);
      const newScale = Math.max(10, Math.min(80, Math.round(scale * (distNow / distStart))));
      onScaleChange?.(newScale);
    }
  }
  function handlePointerUp() {
    dragKind.current = null;
    resizeStart.current = null;
  }
  function startResize(e: React.PointerEvent) {
    if (!onScaleChange || !containerRef.current) return;
    e.stopPropagation();
    const rect = containerRef.current.getBoundingClientRect();
    resizeStart.current = {
      cx: rect.left + (config.position_x_pct / 100) * rect.width,
      cy: rect.top + (config.position_y_pct / 100) * rect.height,
      x: e.clientX,
      y: e.clientY,
      scale: config.scale_width_pct,
    };
    dragKind.current = "resize";
    (e.target as Element).setPointerCapture(e.pointerId);
  }

  return (
    <div className={className ?? ""}>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Previsualización 9:16
        </p>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setShowSafeZones((v) => !v)}
          className="h-6 gap-1 text-xs"
        >
          {showSafeZones ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
          Zonas seguras
        </Button>
      </div>

      <div
        ref={containerRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        className="relative mx-auto cursor-crosshair touch-none select-none overflow-hidden rounded-lg border bg-gradient-to-br from-slate-900 via-slate-800 to-slate-950"
        style={{ aspectRatio: "9 / 16", maxWidth: "280px" }}
      >
        <div
          className="pointer-events-none absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "radial-gradient(circle at 30% 20%, rgba(255,255,255,0.06), transparent 50%), radial-gradient(circle at 70% 80%, rgba(34,211,238,0.08), transparent 50%)",
          }}
        />

        {showSafeZones && <SafeZonesOverlay />}

        {/* Placeholder de la foto (recuadro con icono) en posición/tamaño */}
        <div
          className="pointer-events-none absolute"
          style={{
            left: `${config.position_x_pct}%`,
            top: `${config.position_y_pct}%`,
            width: `${config.scale_width_pct}%`,
            transform: "translate(-50%, -50%)",
          }}
        >
          <div
            className="flex aspect-square w-full flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed border-brand-cyan/70 bg-brand-cyan/10"
          >
            <ImageIcon className="h-5 w-5 text-brand-cyan/80" />
            <span className="text-[8px] font-medium text-brand-cyan/80">FOTO</span>
          </div>
          {onScaleChange && (
            <div
              onPointerDown={startResize}
              className="pointer-events-auto absolute -bottom-1.5 -right-1.5 h-3 w-3 cursor-nwse-resize rounded-sm border border-white bg-brand-cyan shadow"
              title="Arrastra para cambiar el tamaño"
              style={{ transform: "rotate(45deg)" }}
            />
          )}
        </div>

        <div className="pointer-events-none absolute right-1 top-1 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[9px] text-white/80">
          {config.position_x_pct}%, {config.position_y_pct}% · {config.scale_width_pct}%
        </div>
      </div>
      <p className="mt-2 text-center text-[10px] text-muted-foreground">
        Click/drag para mover · esquina ◤ para redimensionar · la foto real se
        descarga al generar
      </p>
    </div>
  );
}

// Safe-zones idénticas a Sticker/Subs preview.
function SafeZonesOverlay() {
  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[12%] border-b border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute left-1 top-1 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI top
        </span>
      </div>
      <div className="pointer-events-none absolute bottom-[18%] right-0 top-[15%] w-[12%] border-l border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute right-1 top-1 rotate-90 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI lat.
        </span>
      </div>
      <div className="pointer-events-none absolute bottom-[18%] left-0 top-[15%] w-[12%] border-r border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute left-1 top-1 -rotate-90 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI lat.
        </span>
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[18%] border-t border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute bottom-1 left-1 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI bottom
        </span>
      </div>
    </>
  );
}
