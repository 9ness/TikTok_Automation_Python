"use client";

import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Eye,
  EyeOff,
  ImageIcon,
} from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { arrowStickerPreview } from "@/lib/queries/editor-auto";
import { useFontByPath, useFontFamily } from "@/lib/queries/fonts";
import { cn } from "@/lib/utils";

/**
 * Previsualización 9:16 CENTRALIZADA del flujo del Editor Auto.
 *
 * Muestra TODOS los overlays de las herramientas activas a la vez
 * (subtítulos de muestra + flecha CTA + foto) sobre un único frame 9:16
 * con zonas seguras. Un selector (chips) elige qué elemento ajustar; ese
 * elemento se mueve/redimensiona con el dedo (touch) y la flecha además
 * rota. Reemplaza los previews individuales de cada tarjeta.
 */

type StepLike = {
  tool_id: string;
  enabled: boolean;
  config: Record<string, unknown>;
};

type ElementId = "subs_auto" | "sticker_arrow" | "photo_insert";

const SAMPLE_WORDS = ["PREVIEW", "DEL", "FLUJO", "EN", "DIRECTO"];

export function FlowPreview9x16({
  steps,
  onConfigChange,
  className,
}: {
  steps: StepLike[];
  /** Actualiza la config de la herramienta `toolId`. */
  onConfigChange: (toolId: ElementId, key: string, value: unknown) => void;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dragKind = useRef<"move" | "resize" | null>(null);
  const resizeStart = useRef<{ cx: number; cy: number; x: number; y: number; scale: number } | null>(null);
  const [showSafe, setShowSafe] = useState(true);

  const subs = steps.find((s) => s.enabled && s.tool_id === "subs_auto") ?? null;
  const arrow = steps.find((s) => s.enabled && s.tool_id === "sticker_arrow") ?? null;
  const photo = steps.find((s) => s.enabled && s.tool_id === "photo_insert") ?? null;

  const elements: { id: ElementId; label: string }[] = [
    subs ? { id: "subs_auto" as const, label: "Subtítulos" } : null,
    arrow ? { id: "sticker_arrow" as const, label: "Flecha" } : null,
    photo ? { id: "photo_insert" as const, label: "Foto" } : null,
  ].filter(Boolean) as { id: ElementId; label: string }[];

  const [selectedRaw, setSelected] = useState<ElementId | null>(null);
  const selected: ElementId | null =
    selectedRaw && elements.some((e) => e.id === selectedRaw)
      ? selectedRaw
      : (elements[0]?.id ?? null);

  // ── Subs styling ──
  const subsCfg = subs?.config ?? {};
  const subsFont = useFontByPath(String(subsCfg.font_path ?? ""));
  const subsFamily = useFontFamily(subsFont);
  const subsY = Number(subsCfg.y_position ?? 0.78);
  const subsMaxWords = Number(subsCfg.max_words ?? 3);
  const subsMaxWidth = Number(subsCfg.max_width ?? 0.85);
  const subsFontCqi = Number(subsCfg.font_scale ?? 0.045) * 100 * (16 / 9);

  // ── Arrow asset ──
  const arrowFile = String(arrow?.config.sticker_file ?? "");
  const arrowAsset = arrowFile ? arrowStickerPreview(arrowFile) : null;
  const arrowRot = Number(arrow?.config.rotation_deg ?? 0);
  const arrowCss = [
    arrow?.config.flip_horizontal ? "scaleX(-1)" : "",
    arrow?.config.flip_vertical ? "scaleY(-1)" : "",
    arrowRot ? `rotate(${arrowRot}deg)` : "",
  ]
    .filter(Boolean)
    .join(" ");

  // ── Pos helpers per element ──
  function pos(el: ElementId): { x: number; y: number; scale: number } {
    if (el === "subs_auto") return { x: 50, y: subsY * 100, scale: subsMaxWidth * 100 };
    const c = (el === "sticker_arrow" ? arrow : photo)?.config ?? {};
    return {
      x: Number(c.position_x_pct ?? 50),
      y: Number(c.position_y_pct ?? (el === "sticker_arrow" ? 80 : 28)),
      scale: Number(c.scale_width_pct ?? (el === "sticker_arrow" ? 25 : 38)),
    };
  }

  function applyMove(clientX: number, clientY: number) {
    if (!selected || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const xPct = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
    const yPct = Math.max(0, Math.min(100, ((clientY - rect.top) / rect.height) * 100));
    if (selected === "subs_auto") {
      onConfigChange("subs_auto", "y_position", Number((yPct / 100).toFixed(2)));
    } else {
      onConfigChange(selected, "position_x_pct", Math.round(xPct));
      onConfigChange(selected, "position_y_pct", Math.round(yPct));
    }
  }

  function handlePointerDown(e: React.PointerEvent) {
    if (!selected) return;
    dragKind.current = "move";
    (e.target as Element).setPointerCapture(e.pointerId);
    applyMove(e.clientX, e.clientY);
  }
  function handlePointerMove(e: React.PointerEvent) {
    if (dragKind.current === "move") {
      applyMove(e.clientX, e.clientY);
    } else if (dragKind.current === "resize" && resizeStart.current && selected) {
      const { cx, cy, x, y, scale } = resizeStart.current;
      const distStart = Math.hypot(x - cx, y - cy) || 1;
      const distNow = Math.hypot(e.clientX - cx, e.clientY - cy);
      const newScale = Math.max(10, Math.min(80, Math.round(scale * (distNow / distStart))));
      onConfigChange(selected, "scale_width_pct", newScale);
    }
  }
  function handlePointerUp() {
    dragKind.current = null;
    resizeStart.current = null;
  }
  function startResize(e: React.PointerEvent) {
    if (!selected || selected === "subs_auto" || !containerRef.current) return;
    e.stopPropagation();
    const rect = containerRef.current.getBoundingClientRect();
    const p = pos(selected);
    resizeStart.current = {
      cx: rect.left + (p.x / 100) * rect.width,
      cy: rect.top + (p.y / 100) * rect.height,
      x: e.clientX,
      y: e.clientY,
      scale: p.scale,
    };
    dragKind.current = "resize";
    (e.target as Element).setPointerCapture(e.pointerId);
  }

  if (elements.length === 0) {
    return (
      <div className={cn("text-xs text-muted-foreground", className)}>
        Activa alguna herramienta visual (subtítulos, flecha o foto) para ver la
        previsualización.
      </div>
    );
  }

  const subsChunk = SAMPLE_WORDS.slice(0, Math.max(1, Math.min(subsMaxWords, SAMPLE_WORDS.length)));
  const subsActiveIdx = Math.min(2, subsChunk.length - 1);

  const QUICK_ROTATIONS = [
    { deg: 270, Icon: ArrowUp, label: "Arriba" },
    { deg: 90, Icon: ArrowDown, label: "Abajo" },
    { deg: 180, Icon: ArrowLeft, label: "Izquierda" },
    { deg: 0, Icon: ArrowRight, label: "Derecha" },
  ];

  return (
    <div className={className}>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Previsualización 9:16 · ajusta aquí
        </p>
        <Button size="sm" variant="ghost" onClick={() => setShowSafe((v) => !v)} className="h-6 gap-1 text-xs">
          {showSafe ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
          Zonas seguras
        </Button>
      </div>

      {/* Selector de qué elemento ajustar */}
      <div className="mb-2 flex flex-wrap items-center justify-center gap-1">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Ajustar:
        </span>
        {elements.map((el) => (
          <Button
            key={el.id}
            type="button"
            size="sm"
            variant={selected === el.id ? "default" : "outline"}
            className="h-6 px-2 text-[11px]"
            onClick={() => setSelected(el.id)}
          >
            {el.label}
          </Button>
        ))}
      </div>

      {/* Rotación — solo cuando la flecha está seleccionada */}
      {selected === "sticker_arrow" && (
        <div className="mb-2 flex items-center justify-center gap-1">
          <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Apuntar:
          </span>
          {QUICK_ROTATIONS.map(({ deg, Icon, label }) => (
            <Button
              key={deg}
              type="button"
              size="icon"
              variant={arrowRot % 360 === deg ? "default" : "outline"}
              className="h-6 w-6"
              onClick={() => onConfigChange("sticker_arrow", "rotation_deg", deg)}
              title={`${label} (${deg}°)`}
            >
              <Icon className="h-3 w-3" />
            </Button>
          ))}
        </div>
      )}

      <div
        ref={containerRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        className="relative mx-auto cursor-crosshair touch-none select-none overflow-hidden rounded-lg border bg-gradient-to-br from-slate-900 via-slate-800 to-slate-950"
        style={{ aspectRatio: "9 / 16", maxWidth: "300px", containerType: "size" }}
      >
        <div
          className="pointer-events-none absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "radial-gradient(circle at 30% 20%, rgba(255,255,255,0.06), transparent 50%), radial-gradient(circle at 70% 80%, rgba(34,211,238,0.08), transparent 50%)",
          }}
        />
        {showSafe && <SafeZonesOverlay />}

        {/* ── Foto (placeholder) ── */}
        {photo && (
          <ElementBox active={selected === "photo_insert"} p={pos("photo_insert")}>
            <div className="flex aspect-square w-full flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed border-brand-cyan/70 bg-brand-cyan/10">
              <ImageIcon className="h-5 w-5 text-brand-cyan/80" />
              <span className="text-[8px] font-medium text-brand-cyan/80">FOTO</span>
            </div>
            {selected === "photo_insert" && <ResizeHandle onPointerDown={startResize} />}
          </ElementBox>
        )}

        {/* ── Flecha ── */}
        {arrow && (
          <ElementBox active={selected === "sticker_arrow"} p={pos("sticker_arrow")}>
            <div style={{ transform: arrowCss, transformOrigin: "center" }}>
              {arrowAsset ? (
                arrowAsset.asImage ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={arrowAsset.url} alt="flecha" className="block h-auto w-full" draggable={false} />
                ) : (
                  <video src={arrowAsset.url} autoPlay loop muted playsInline className="block h-auto w-full" />
                )
              ) : (
                <div className="flex aspect-square w-full items-center justify-center rounded border border-dashed border-amber-400/60 text-[8px] text-amber-300">
                  flecha
                </div>
              )}
            </div>
            {selected === "sticker_arrow" && <ResizeHandle onPointerDown={startResize} />}
          </ElementBox>
        )}

        {/* ── Subtítulos (muestra) ── */}
        {subs && (
          <>
            <div
              className="pointer-events-none absolute flex flex-wrap items-center justify-center text-center"
              style={{
                left: "50%",
                top: `${subsY * 100}%`,
                transform: "translate(-50%, -50%)",
                width: `${subsMaxWidth * 100}%`,
                gap: "0.2em",
                fontSize: `${subsFontCqi}cqi`,
                fontFamily: subsFamily,
                fontWeight: subsFont?.source === "bundled" ? "normal" : 900,
                lineHeight: 1.05,
                opacity: selected === "subs_auto" ? 1 : 0.85,
                textShadow: buildStroke(subsCfg),
              }}
            >
              {subsChunk.map((w, i) => (
                <span key={i} className="inline-block" style={subHighlight(subsCfg, i === subsActiveIdx)}>
                  {transformCase(w, String(subsCfg.case_mode ?? "UPPERCASE"))}
                </span>
              ))}
            </div>
            {selected === "subs_auto" && (
              <span
                className="pointer-events-none absolute left-1 z-10 rounded bg-cyan-500/80 px-1 text-[8px] font-medium text-black"
                style={{ top: `calc(${subsY * 100}% - 6px)` }}
              >
                Y={subsY.toFixed(2)}
              </span>
            )}
          </>
        )}

        <div className="pointer-events-none absolute right-1 top-1 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[9px] text-white/80">
          {selected === "subs_auto"
            ? `Y ${subsY.toFixed(2)}`
            : selected
              ? `${pos(selected).x}%, ${pos(selected).y}% · ${pos(selected).scale}%`
              : ""}
        </div>
      </div>
      <p className="mt-2 text-center text-[10px] text-muted-foreground">
        {selected === "subs_auto"
          ? "Arrastra vertical para mover los subtítulos"
          : "Arrastra para mover · esquina ◤ para redimensionar"}
      </p>
    </div>
  );
}

function ElementBox({
  active,
  p,
  children,
}: {
  active: boolean;
  p: { x: number; y: number; scale: number };
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn("pointer-events-none absolute", active && "z-10")}
      style={{
        left: `${p.x}%`,
        top: `${p.y}%`,
        width: `${p.scale}%`,
        transform: "translate(-50%, -50%)",
      }}
    >
      {children}
    </div>
  );
}

function ResizeHandle({ onPointerDown }: { onPointerDown: (e: React.PointerEvent) => void }) {
  return (
    <div
      onPointerDown={onPointerDown}
      className="pointer-events-auto absolute -bottom-1.5 -right-1.5 h-3 w-3 cursor-nwse-resize rounded-sm border border-white bg-brand-cyan shadow"
      title="Arrastra para cambiar el tamaño"
      style={{ transform: "rotate(45deg)" }}
    />
  );
}

function SafeZonesOverlay() {
  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[12%] border-b border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute left-1 top-1 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">UI top</span>
      </div>
      <div className="pointer-events-none absolute bottom-[18%] right-0 top-[15%] w-[12%] border-l border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute right-1 top-1 rotate-90 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">UI lat.</span>
      </div>
      <div className="pointer-events-none absolute bottom-[18%] left-0 top-[15%] w-[12%] border-r border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute left-1 top-1 -rotate-90 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">UI lat.</span>
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[18%] border-t border-dashed border-amber-400/40 bg-amber-400/5">
        <span className="absolute bottom-1 left-1 rounded bg-amber-500/80 px-1 py-0.5 text-[8px] font-medium text-black">UI bottom</span>
      </div>
    </>
  );
}

// ── Helpers de subtítulos (espejo de SubsPreview9x16) ──
function transformCase(text: string, mode: string): string {
  if (mode === "UPPERCASE") return text.toUpperCase();
  if (mode === "lowercase") return text.toLowerCase();
  if (mode === "Title Case")
    return text.replace(/\w\S*/g, (w) => w[0]!.toUpperCase() + w.slice(1).toLowerCase());
  return text;
}

function buildStroke(cfg: Record<string, unknown>): string {
  const sw = Number(cfg.stroke_width ?? 3);
  if (sw <= 0) return "none";
  const em = sw / 80;
  const stroke = String(cfg.stroke_color ?? "#000000");
  const dirs: [number, number][] = [
    [-1, -1], [0, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [0, 1], [1, 1],
  ];
  return dirs.map(([dx, dy]) => `${(dx * em).toFixed(3)}em ${(dy * em).toFixed(3)}em 0 ${stroke}`).join(", ");
}

function subHighlight(cfg: Record<string, unknown>, active: boolean): React.CSSProperties {
  const textColor = String(cfg.text_color ?? "#FFFFFF");
  const hl = String(cfg.highlight_color ?? "#BB0808");
  const base: React.CSSProperties = { color: textColor, padding: "0 0.05em" };
  if (!active) return base;
  switch (String(cfg.highlight_mode ?? "pill")) {
    case "pill":
      return { ...base, backgroundColor: hl, padding: "0.12em 0.3em", borderRadius: "0.1em" };
    case "color_swap":
      return { ...base, color: hl };
    case "underline":
      return { ...base, textDecoration: `underline ${hl}`, textUnderlineOffset: "0.15em", textDecorationThickness: "0.1em" };
    case "glow":
      return { ...base, textShadow: `0 0 10px ${hl}, 0 0 20px ${hl}` };
    default:
      return base;
  }
}
