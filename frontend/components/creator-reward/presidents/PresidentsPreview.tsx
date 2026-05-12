"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useFonts, useFontFamily, type FontItem } from "@/lib/queries/fonts";
import type {
  PresidentsHookConfig,
  PresidentsSubsConfig,
} from "@/lib/types/creator-reward";
import { cn } from "@/lib/utils";

/**
 * Previsualización 9:16 estilo TikTok con zonas seguras + subtítulos +
 * hook box renderizados con la config actual (live).
 *
 * Calibración de tamaño:
 *   El backend usa `font_scale` relativo al HEIGHT del vídeo (h=1920px →
 *   0.040 ≈ 77px). En el frame del preview 9:16, calculamos el tamaño en
 *   `cqi` (= % del ancho del contenedor): height/width = 16/9, así que
 *   `font_scale * (16/9) * 100` cqi reproduce el ratio correcto
 *   independientemente del tamaño real del frame.
 */
export function PresidentsPreview({
  subs,
  hook,
  className,
}: {
  subs: PresidentsSubsConfig;
  hook: PresidentsHookConfig;
  className?: string;
}) {
  const [showSafeZones, setShowSafeZones] = useState(true);

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Previsualización 9:16</p>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setShowSafeZones((v) => !v)}
          className="h-7 gap-1 text-xs"
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
        className="relative mx-auto overflow-hidden rounded-lg border bg-gradient-to-br from-slate-900 via-slate-800 to-slate-950"
        style={{
          aspectRatio: "9 / 16",
          maxWidth: "320px",
          // Habilita unidades cqi/cqh para que los font sizes escalen
          // proporcionalmente al frame y no al viewport.
          containerType: "size",
        }}
      >
        {/* Fondo simulando un "frame" de vídeo */}
        <div
          className="absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "radial-gradient(circle at 30% 20%, rgba(255,255,255,0.06), transparent 50%), radial-gradient(circle at 70% 80%, rgba(34,211,238,0.08), transparent 50%)",
          }}
        />

        {/* OVERLAY ZONAS SEGURAS TIKTOK */}
        {showSafeZones && <SafeZonesOverlay maxWidthPct={subs.max_width * 100} />}

        {/* HOOK BOX (live) */}
        {hook.enabled && (
          <HookBoxPreview hook={hook} showLabel={showSafeZones} />
        )}

        {/* SUBTÍTULOS (live) */}
        {subs.enabled && (
          <SubtitlesPreview subs={subs} showLabel={showSafeZones} />
        )}
      </div>

      <p className="text-center text-[10px] text-muted-foreground">
        Vista aproximada · el render final puede variar ligeramente
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

      {/* Indicadores del ancho máximo de subs (max_width) */}
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
// Subtítulos karaoke
// ---------------------------------------------------------------------------
const SAMPLE_WORDS = [
  "MORE",
  "FRAGILE",
  "THAN",
  "EVER",
  "BEFORE",
  "RECORDED",
  "EVIDENCE",
  "AVAILABLE",
];

// Mapping de fuente backend → CSS font-family + font-weight.
// Pesos por nombre — solo se usa como fallback si el registry no lo conoce.
// El registry universal cubre cualquier fuente (system + bundled).
const FONT_WEIGHT_BY_NAME: Record<string, number> = {
  Impact: 900,
  "Arial Black": 900,
  "Rubik Bold": 700,
  "Arial Bold": 700,
};

function transformCase(text: string, mode: PresidentsSubsConfig["case_mode"]): string {
  switch (mode) {
    case "UPPERCASE":
      return text.toUpperCase();
    case "lowercase":
      return text.toLowerCase();
    case "Title Case":
      return text.replace(/\w\S*/g, (w) => w[0]!.toUpperCase() + w.slice(1).toLowerCase());
    case "None":
    default:
      return text;
  }
}

function SubtitlesPreview({
  subs,
  showLabel,
}: {
  subs: PresidentsSubsConfig;
  showLabel: boolean;
}) {
  const chunk = SAMPLE_WORDS.slice(0, Math.min(subs.max_words, SAMPLE_WORDS.length));
  // Palabra activa = la del medio del chunk para que se note el highlight.
  const activeIdx = Math.min(2, chunk.length - 1);

  // font_scale 0.04 con height/width = 16/9 → font_scale * 177.8 cqi
  const fontSizeCqi = subs.font_scale * 100 * (16 / 9);
  const yPosPct = subs.y_position * 100;
  // Resolución dinámica de fuente vía registry — soporta cualquier fuente
  // del proyecto (system o bundled, incluidas las que el usuario sube).
  const fonts = useFonts();
  const entry: FontItem | null =
    fonts.data?.items.find((f) => f.name === subs.font_choice) ?? null;
  const family = useFontFamily(entry);
  // Bundled: peso natural del archivo TTF (no faux-bold). System: usa el
  // peso conocido del nombre.
  const weight =
    entry?.source === "bundled"
      ? "normal"
      : FONT_WEIGHT_BY_NAME[subs.font_choice] ?? 900;
  const fontDef = { family, weight };

  return (
    <>
      {showLabel && (
        <span
          className="pointer-events-none absolute left-1 z-10 -translate-y-1/2 rounded bg-cyan-500/80 px-1 py-0.5 text-[8px] font-medium text-black"
          style={{ top: `${yPosPct}%` }}
        >
          subs Y={subs.y_position.toFixed(2)}
        </span>
      )}
      <div
        className="absolute flex flex-wrap items-center justify-center gap-x-[0.2em] gap-y-1 text-center"
        style={{
          left: "50%",
          top: `${yPosPct}%`,
          transform: "translate(-50%, -50%)",
          width: `${subs.max_width * 100}%`,
          fontFamily: fontDef.family,
          fontWeight: fontDef.weight,
          fontSynthesis: "none",
          fontSize: `${fontSizeCqi}cqi`,
          lineHeight: 1.05,
          letterSpacing: "0.01em",
          textShadow: buildTextEffects(subs),
        }}
      >
        {chunk.map((word, i) => {
          const display = transformCase(word, subs.case_mode);
          const active = i === activeIdx;
          return (
            <span
              key={i}
              className="inline-block"
              style={highlightStyle(subs, active)}
            >
              {display}
            </span>
          );
        })}
      </div>
    </>
  );
}

/**
 * Combina stroke (perímetro) + drop shadow en text-shadow.
 *
 * Usamos `text-shadow` (NO `filter: drop-shadow()`) para que el shadow
 * SOLO afecte los glyphs del texto, no al pill rojo de fondo.
 *
 * - Stroke: 8 direcciones sólidas sin blur — em proporcional al stroke_width
 * - Drop shadow: distance+angle CapCut → offset, blur opcional, color rgba
 */
function buildTextEffects(subs: PresidentsSubsConfig): string {
  const parts: string[] = [];

  if (subs.stroke_width > 0) {
    const em = subs.stroke_width / 80;
    const dirs: [number, number][] = [
      [-1, -1], [0, -1], [1, -1],
      [-1, 0],           [1, 0],
      [-1, 1],  [0, 1],  [1, 1],
    ];
    for (const [dx, dy] of dirs) {
      parts.push(`${(dx * em).toFixed(3)}em ${(dy * em).toFixed(3)}em 0 ${subs.stroke_color}`);
    }
  }

  if (subs.shadow_enabled) {
    const dEm = subs.shadow_distance / 40; // 8/40 = 0.2em (visible)
    const rad = (subs.shadow_angle * Math.PI) / 180;
    const dx = dEm * Math.cos(rad);
    const dy = dEm * Math.abs(Math.sin(rad)); // CSS Y positivo = abajo
    const blurEm = subs.shadow_blur / 150;
    const hex = subs.shadow_color.replace("#", "");
    const r = parseInt(hex.slice(0, 2), 16) || 0;
    const g = parseInt(hex.slice(2, 4), 16) || 0;
    const b = parseInt(hex.slice(4, 6), 16) || 0;
    parts.push(
      `${dx.toFixed(3)}em ${dy.toFixed(3)}em ${blurEm.toFixed(3)}em rgba(${r},${g},${b},${subs.shadow_opacity})`,
    );
  }

  return parts.length > 0 ? parts.join(", ") : "none";
}

function highlightStyle(
  subs: PresidentsSubsConfig,
  active: boolean,
): React.CSSProperties {
  const base: React.CSSProperties = {
    color: subs.text_color,
    padding: "0 0.05em",
  };
  if (!active) return base;

  switch (subs.highlight_mode) {
    case "pill":
      // CapCut Classic: pill compacto pegado al texto, padding mínimo,
      // esquinas casi rectas. El stroke negro del texto + fondo rojo dan
      // el look típico de subs virales de TikTok.
      return {
        ...base,
        backgroundColor: subs.highlight_color,
        color: subs.text_color,
        padding: "0.12em 0.3em",
        borderRadius: "0.1em",
      };
    case "color_swap":
      return { ...base, color: subs.highlight_color };
    case "underline":
      return {
        ...base,
        textDecoration: `underline ${subs.highlight_color}`,
        textUnderlineOffset: "0.15em",
        textDecorationThickness: "0.1em",
      };
    case "box_outline":
      return {
        ...base,
        boxShadow: `inset 0 0 0 0.1em ${subs.highlight_color}`,
      };
    case "glow":
      return {
        ...base,
        textShadow: `0 0 10px ${subs.highlight_color}, 0 0 20px ${subs.highlight_color}`,
      };
    case "none":
    default:
      return base;
  }
}

// ---------------------------------------------------------------------------
// Hook box — caja compacta blanca con borde rojo brillante + glow (CapCut)
// ---------------------------------------------------------------------------
const SAMPLE_HOOK_TEXT = "Did the most Damage to the America";

function HookBoxPreview({
  hook,
  showLabel,
}: {
  hook: PresidentsHookConfig;
  showLabel: boolean;
}) {
  const yPosPct = hook.y_position * 100;
  // El hook usa font_scale ~0.02 (más pequeño que subs). Misma calibración.
  const fontSizeCqi = hook.font_scale * 100 * (16 / 9);

  return (
    <>
      {showLabel && (
        <span
          className="pointer-events-none absolute left-1 z-10 -translate-y-1/2 rounded bg-rose-500/80 px-1 py-0.5 text-[8px] font-medium text-black"
          style={{ top: `${yPosPct}%` }}
        >
          hook Y={hook.y_position.toFixed(2)}
        </span>
      )}
      <div
        className="absolute"
        style={{
          left: "50%",
          top: `${yPosPct}%`,
          transform: "translate(-50%, -50%)",
          maxWidth: "85%",
        }}
      >
        {/* Wrapper relativo: la sombra roja va en un div absoluto detrás
            con ESQUINAS DURAS (sin border-radius) offset abajo-izquierda
            estilo CapCut. La caja blanca va encima rounded. */}
        <div className="relative inline-block">
          <div
            aria-hidden
            className="absolute inset-0"
            style={{
              backgroundColor: hook.shadow_color,
              transform: "translate(-0.35em, 0.35em)",
              // Sin border-radius — esquinas duras como en CapCut
            }}
          />
          <div
            className="relative text-center font-bold"
            style={{
              backgroundColor: hook.box_color,
              color: hook.text_color,
              // Backend `text_hook.py` usa border_radius=0 → esquinas duras
              borderRadius: 0,
              padding: "0.35em 0.7em",
              fontSize: `${fontSizeCqi}cqi`,
              fontFamily: "var(--font-rubik), 'Arial Black', sans-serif",
              lineHeight: 1.15,
              letterSpacing: "0.01em",
              wordSpacing: "0.05em",
            }}
          >
            {SAMPLE_HOOK_TEXT}
          </div>
        </div>
      </div>
    </>
  );
}
