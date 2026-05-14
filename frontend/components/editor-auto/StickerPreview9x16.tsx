"use client";

import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Eye,
  EyeOff,
} from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { arrowStickerPreview } from "@/lib/queries/editor-auto";

/**
 * Previsualización 9:16 estilo TikTok para el `sticker_arrow`. Permite:
 *   - Click/drag dentro del frame → reposiciona el CENTRO del sticker.
 *   - Drag de la esquina inferior-derecha → cambia el tamaño en vivo.
 *   - Rotación 0/90/180/270 y espejado hflip/vflip (CSS transforms).
 *
 * Las safe-zones replican el estilo del `SubsPreview9x16`: bandas UI
 * superior/lateral/inferior de TikTok con borde discontinuo amarillo.
 *
 * El asset se carga vía `arrowStickerPreview()` que decide:
 *   - MOV → transcodificado a APNG en backend (`?as=apng`) → `<img>`
 *   - WebM → directo → `<video>` (alpha nativo del browser)
 *   - GIF/PNG/APNG → directo → `<img>`
 */

export interface StickerPreviewConfig {
  sticker_file: string;
  position_x_pct: number;
  position_y_pct: number;
  scale_width_pct: number;
  rotation_deg: number;
  flip_horizontal: boolean;
  flip_vertical: boolean;
}

export function StickerPreview9x16({
  config,
  onPositionChange,
  onScaleChange,
  onRotationChange,
  className,
}: {
  config: StickerPreviewConfig;
  onPositionChange?: (xPct: number, yPct: number) => void;
  /** Cambia `scale_width_pct` al arrastrar la esquina inferior derecha. */
  onScaleChange?: (scalePct: number) => void;
  /** Aplica una rotación absoluta (0/90/180/270) desde los botones rápidos. */
  onRotationChange?: (deg: number) => void;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dragKind = useRef<"move" | "resize" | null>(null);
  const resizeStart = useRef<{
    x: number;
    y: number;
    cx: number;
    cy: number;
    scale: number;
  } | null>(null);
  const [showSafeZones, setShowSafeZones] = useState(true);

  const hasSticker = Boolean(config.sticker_file);
  const preview = hasSticker ? arrowStickerPreview(config.sticker_file) : null;

  // Transform CSS: orden flip → rotate (mismo que el FFmpeg backend).
  const cssTransform = [
    config.flip_horizontal ? "scaleX(-1)" : "",
    config.flip_vertical ? "scaleY(-1)" : "",
    config.rotation_deg ? `rotate(${config.rotation_deg}deg)` : "",
  ]
    .filter(Boolean)
    .join(" ");

  const updatePos = (clientX: number, clientY: number) => {
    if (!onPositionChange || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const xPct = Math.max(
      0,
      Math.min(100, ((clientX - rect.left) / rect.width) * 100),
    );
    const yPct = Math.max(
      0,
      Math.min(100, ((clientY - rect.top) / rect.height) * 100),
    );
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
      const { x, y, cx, cy, scale } = resizeStart.current;
      // Distancia desde el centro al cursor (en px del contenedor) escala
      // proporcionalmente al ancho del sticker. Usamos max(dx, dy) para
      // que arrastrar en cualquier dirección agrande/empequeñezca.
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const dxStart = x - cx;
      const dyStart = y - cy;
      const dxNow = e.clientX - cx;
      const dyNow = e.clientY - cy;
      const distStart = Math.hypot(dxStart, dyStart) || 1;
      const distNow = Math.hypot(dxNow, dyNow);
      const ratio = distNow / distStart;
      const newScale = Math.max(5, Math.min(80, Math.round(scale * ratio)));
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
    const cx = rect.left + (config.position_x_pct / 100) * rect.width;
    const cy = rect.top + (config.position_y_pct / 100) * rect.height;
    resizeStart.current = {
      x: e.clientX,
      y: e.clientY,
      cx,
      cy,
      scale: config.scale_width_pct,
    };
    dragKind.current = "resize";
    (e.target as Element).setPointerCapture(e.pointerId);
  }

  // Botones de rotación rápida — establecen el ángulo absoluto. El
  // asset original suele apuntar a la derecha (→), así que mapeamos:
  //   →  0°  · ↓ 90°  · ←  180°  · ↑ 270°
  // Si el asset apuntara originalmente arriba, el operador combina
  // estos con los flips para llegar a cualquier orientación.
  const QUICK_ROTATIONS: { deg: number; label: string; Icon: typeof ArrowUp }[] = [
    { deg: 270, label: "Arriba", Icon: ArrowUp },
    { deg: 90, label: "Abajo", Icon: ArrowDown },
    { deg: 180, label: "Izquierda", Icon: ArrowLeft },
    { deg: 0, label: "Derecha", Icon: ArrowRight },
  ];

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
          {showSafeZones ? (
            <Eye className="h-3 w-3" />
          ) : (
            <EyeOff className="h-3 w-3" />
          )}
          Zonas seguras
        </Button>
      </div>
      {onRotationChange && (
        <div className="mb-2 flex items-center justify-center gap-1">
          <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Apuntar:
          </span>
          {QUICK_ROTATIONS.map(({ deg, label, Icon }) => {
            const active = (config.rotation_deg ?? 0) % 360 === deg;
            return (
              <Button
                key={deg}
                type="button"
                size="icon"
                variant={active ? "default" : "outline"}
                className="h-6 w-6"
                onClick={() => onRotationChange(deg)}
                title={`${label} (${deg}°)`}
              >
                <Icon className="h-3 w-3" />
              </Button>
            );
          })}
        </div>
      )}

      <div
        ref={containerRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        className="relative mx-auto cursor-crosshair touch-none select-none overflow-hidden rounded-lg border bg-gradient-to-br from-slate-900 via-slate-800 to-slate-950"
        style={{ aspectRatio: "9 / 16", maxWidth: "280px" }}
      >
        {/* Fake frame gradient — simula vídeo de fondo */}
        <div
          className="pointer-events-none absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "radial-gradient(circle at 30% 20%, rgba(255,255,255,0.06), transparent 50%), radial-gradient(circle at 70% 80%, rgba(34,211,238,0.08), transparent 50%)",
          }}
        />

        {showSafeZones && <SafeZonesOverlay />}

        {hasSticker && preview ? (
          <div
            className="pointer-events-none absolute"
            style={{
              left: `${config.position_x_pct}%`,
              top: `${config.position_y_pct}%`,
              width: `${config.scale_width_pct}%`,
              // Centro del sticker en (left, top); transformaciones después.
              transform: `translate(-50%, -50%) ${cssTransform}`,
              transformOrigin: "center",
            }}
          >
            {preview.asImage ? (
              <img
                key={preview.url}
                src={preview.url}
                alt={config.sticker_file}
                className="block h-auto w-full"
                draggable={false}
              />
            ) : (
              <video
                key={preview.url}
                src={preview.url}
                autoPlay
                loop
                muted
                playsInline
                className="block h-auto w-full"
              />
            )}
            {onScaleChange && (
              <div
                onPointerDown={startResize}
                className="pointer-events-auto absolute -bottom-1.5 -right-1.5 h-3 w-3 cursor-nwse-resize rounded-sm border border-white bg-brand-cyan shadow"
                title="Arrastra para cambiar el tamaño"
                style={{ transform: "rotate(45deg)" }}
              />
            )}
          </div>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-[11px] text-muted-foreground">
            Elige un sticker
          </div>
        )}
        <div className="pointer-events-none absolute right-1 top-1 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[9px] text-white/80">
          {config.position_x_pct}%, {config.position_y_pct}% ·{" "}
          {config.scale_width_pct}%
        </div>
      </div>
      <p className="mt-2 text-center text-[10px] text-muted-foreground">
        Click/drag para mover · esquina ◤ para redimensionar
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Zonas seguras de TikTok (idéntico al SubsPreview9x16)
// ---------------------------------------------------------------------------
function SafeZonesOverlay() {
  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[12%] border-b border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute left-1 top-1 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI top
        </span>
      </div>
      {/* Lateral derecha — likes / share / comment de TikTok */}
      <div className="pointer-events-none absolute bottom-[18%] right-0 top-[15%] w-[12%] border-l border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute right-1 top-1 rotate-90 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI lat.
        </span>
      </div>
      {/* Lateral izquierda — Following | Para ti + indicador margen seguro */}
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
