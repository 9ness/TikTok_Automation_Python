"use client";

import { Eye, EyeOff } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useFontByPath, useFontFamily } from "@/lib/queries/fonts";

/**
 * Previsualización 9:16 estilo TikTok con zonas seguras + subtítulos
 * renderizados con la config actual (live). Drag vertical sobre el
 * área para mover Y position.
 *
 * Diseño calibrado igual que `PresidentsPreview` / `SubsAutoStyleEditor`:
 *   font_scale del backend = % del HEIGHT del vídeo (h=1920 → 0.040 ≈ 77px).
 *   En el preview 9:16, usamos `cqi` (% del ancho del contenedor) con
 *   ratio height/width = 16/9 → fontSizeCqi = font_scale * 100 * (16/9).
 *
 * El usuario aún no ha subido el vídeo cuando configura el flujo, así que
 * el fondo es un gradient placeholder (no frame real). El render final
 * preserva las MISMAS proporciones porque se calcula con font_scale
 * relativo al HEIGHT en ambos casos.
 */

export interface SubsPreviewConfig {
  font_path: string;
  highlight_mode: string;
  highlight_color: string;
  text_color: string;
  stroke_color: string;
  stroke_width: number;
  case_mode: string;
  font_scale: number;
  max_words: number;
  y_position: number;
  max_width: number;
}

const SAMPLE_WORDS = [
  "PREVIEW",
  "DEL",
  "FLUJO",
  "EN",
  "DIRECTO",
  "CON",
  "SAFEZONE",
];

export function SubsPreview9x16({
  config,
  onYChange,
  className,
}: {
  config: SubsPreviewConfig;
  onYChange?: (y: number) => void;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef(false);
  const [showSafeZones, setShowSafeZones] = useState(true);

  const selectedFont = useFontByPath(config.font_path);
  const previewFontFamily = useFontFamily(selectedFont);

  const chunk = SAMPLE_WORDS.slice(0, Math.min(config.max_words, SAMPLE_WORDS.length));
  // Activa = la del medio para que se vea el highlight.
  const activeIdx = Math.min(2, chunk.length - 1);

  const fontSizeCqi = config.font_scale * 100 * (16 / 9);
  const yPosPct = config.y_position * 100;
  const maxWidthPct = config.max_width * 100;

  function handlePointerDown(e: React.PointerEvent) {
    if (!onYChange || !containerRef.current) return;
    dragRef.current = true;
    (e.target as Element).setPointerCapture(e.pointerId);
    updateY(e.clientY);
  }
  function handlePointerMove(e: React.PointerEvent) {
    if (!dragRef.current) return;
    updateY(e.clientY);
  }
  function handlePointerUp(e: React.PointerEvent) {
    dragRef.current = false;
    try {
      (e.target as Element).releasePointerCapture(e.pointerId);
    } catch {
      // noop
    }
  }
  function updateY(clientY: number) {
    if (!onYChange || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const ratio = (clientY - rect.top) / rect.height;
    onYChange(Math.max(0, Math.min(1, Number(ratio.toFixed(2)))));
  }

  return (
    <div className={className}>
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

      <div
        ref={containerRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        className={`relative mx-auto overflow-hidden rounded-lg border bg-gradient-to-br from-slate-900 via-slate-800 to-slate-950 ${
          onYChange ? "cursor-ns-resize touch-none select-none" : ""
        }`}
        style={{
          aspectRatio: "9 / 16",
          maxWidth: "280px",
          containerType: "size",
        }}
      >
        {/* "Fake frame" — gradient sutil para simular un vídeo de fondo */}
        <div
          className="absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "radial-gradient(circle at 30% 20%, rgba(255,255,255,0.06), transparent 50%), radial-gradient(circle at 70% 80%, rgba(34,211,238,0.08), transparent 50%)",
          }}
        />

        {showSafeZones && <SafeZonesOverlay maxWidthPct={maxWidthPct} />}

        {/* Línea Y indicator */}
        <div
          className="pointer-events-none absolute inset-x-0 h-px bg-cyan-400/60"
          style={{ top: `${yPosPct}%` }}
        />
        <span
          className="pointer-events-none absolute left-1 z-10 rounded bg-cyan-500/80 px-1 text-[8px] font-medium text-black"
          style={{ top: `calc(${yPosPct}% - 6px)` }}
        >
          Y={config.y_position.toFixed(2)}
        </span>

        {/* Chunk de subs */}
        <div
          className="pointer-events-none absolute flex flex-wrap items-center justify-center text-center"
          style={{
            left: "50%",
            top: `${yPosPct}%`,
            transform: "translate(-50%, -50%)",
            width: `${maxWidthPct}%`,
            gap: "0.2em",
            fontSize: `${fontSizeCqi}cqi`,
            fontFamily: previewFontFamily,
            // Bundled = peso natural del TTF; system = 900 fallback.
            fontWeight: selectedFont?.source === "bundled" ? "normal" : 900,
            fontSynthesis: "none",
            lineHeight: 1.05,
            letterSpacing: "0.01em",
            textShadow: buildStroke(config),
          }}
        >
          {chunk.map((word, i) => (
            <span
              key={i}
              className="inline-block"
              style={highlightStyle(config, i === activeIdx)}
            >
              {transformCase(word, config.case_mode)}
            </span>
          ))}
        </div>
      </div>

      <p className="mt-2 text-center text-[10px] text-muted-foreground">
        {onYChange ? "Arrastra vertical para ajustar Y · " : ""}
        Vista aproximada — el render final preserva proporciones.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Zonas seguras de TikTok
// ---------------------------------------------------------------------------
function SafeZonesOverlay({ maxWidthPct }: { maxWidthPct: number }) {
  return (
    <>
      {/* Top zone — username/handle */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[12%] border-b border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute left-1 top-1 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI top
        </span>
      </div>

      {/* Right zone — like/share/comment */}
      <div className="pointer-events-none absolute bottom-[18%] right-0 top-[15%] w-[12%] border-l border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute right-1 top-1 rotate-90 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI lat.
        </span>
      </div>

      {/* Bottom zone — caption + audio */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[18%] border-t border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute bottom-1 left-1 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">
          UI bottom
        </span>
      </div>

      {/* Indicadores del ancho máximo de subs */}
      <div
        className="pointer-events-none absolute top-[14%] border-r border-dashed border-orange-400/50"
        style={{ left: `${50 + maxWidthPct / 2}%`, height: "70%" }}
      />
      <div
        className="pointer-events-none absolute top-[14%] border-l border-dashed border-orange-400/50"
        style={{ left: `${50 - maxWidthPct / 2}%`, height: "70%" }}
      />
      <span
        className="pointer-events-none absolute -translate-y-1/2 rounded bg-orange-500/80 px-1 py-0.5 text-[8px] font-medium text-black"
        style={{ top: "14%", right: `${(100 - maxWidthPct) / 2}%` }}
      >
        ancho {maxWidthPct.toFixed(0)}%
      </span>
    </>
  );
}

// ---------------------------------------------------------------------------
// Helpers (idénticos al SubsAutoStyleEditor / PresidentsPreview)
// ---------------------------------------------------------------------------
function transformCase(text: string, mode: string): string {
  switch (mode) {
    case "UPPERCASE":
      return text.toUpperCase();
    case "lowercase":
      return text.toLowerCase();
    case "Title Case":
      return text.replace(
        /\w\S*/g,
        (w) => w[0]!.toUpperCase() + w.slice(1).toLowerCase(),
      );
    default:
      return text;
  }
}

function buildStroke(config: SubsPreviewConfig): string {
  if (config.stroke_width <= 0) return "none";
  const em = config.stroke_width / 80;
  const dirs: [number, number][] = [
    [-1, -1], [0, -1], [1, -1],
    [-1, 0],           [1, 0],
    [-1, 1],  [0, 1],  [1, 1],
  ];
  return dirs
    .map(
      ([dx, dy]) =>
        `${(dx * em).toFixed(3)}em ${(dy * em).toFixed(3)}em 0 ${config.stroke_color}`,
    )
    .join(", ");
}

function highlightStyle(
  config: SubsPreviewConfig,
  active: boolean,
): React.CSSProperties {
  const base: React.CSSProperties = {
    color: config.text_color,
    padding: "0 0.05em",
  };
  if (!active) return base;
  switch (config.highlight_mode) {
    case "pill":
      return {
        ...base,
        backgroundColor: config.highlight_color,
        color: config.text_color,
        padding: "0.12em 0.3em",
        borderRadius: "0.1em",
      };
    case "color_swap":
      return { ...base, color: config.highlight_color };
    case "underline":
      return {
        ...base,
        textDecoration: `underline ${config.highlight_color}`,
        textUnderlineOffset: "0.15em",
        textDecorationThickness: "0.1em",
      };
    case "box_outline":
      return {
        ...base,
        boxShadow: `inset 0 0 0 0.08em ${config.highlight_color}`,
        borderRadius: "0.1em",
        padding: "0.05em 0.15em",
      };
    case "glow":
      return {
        ...base,
        textShadow: `0 0 10px ${config.highlight_color}, 0 0 20px ${config.highlight_color}`,
      };
    case "none":
    default:
      return base;
  }
}
