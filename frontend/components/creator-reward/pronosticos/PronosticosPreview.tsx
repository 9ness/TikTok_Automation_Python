"use client";

import { useCallback, useRef, useState } from "react";

import type { PronosticosOverlaysConfig } from "@/lib/types/creator-reward";
import { cn } from "@/lib/utils";

/**
 * Preview 9:16 para Pronósticos Diarios con drag-to-position de los
 * overlays. Los elementos son placeholders visuales aproximados (no fetch
 * de assets reales): sirven para ajustar dónde queremos cada cosa antes
 * de encolar el render real.
 *
 * 4 elementos arrastrables verticalmente:
 *   1) Logos de ligas (durante la intro)            → league_overlay_y_pct
 *   2) Escudos de equipos (single_match izq+dcha)   → team_shield_y_pct
 *   3) Perfil CTA (midroll, centro)                  → profile_cta_y_pct
 *   4) Subtítulos karaoke                            → subtitle_y_pct
 *
 * El usuario arrastra cualquier elemento verticalmente y la posición
 * (0..1) se actualiza en el config. Reset al doble-click.
 */
type DragTarget =
  | "subtitle_y_pct"
  | "league_overlay_y_pct"
  | "team_shield_y_pct"
  | "profile_cta_y_pct";

const RESET_VALUES: Record<DragTarget, number> = {
  subtitle_y_pct: 0.78,
  league_overlay_y_pct: 0.30,
  team_shield_y_pct: 0.43,
  profile_cta_y_pct: 0.36,
};

export function PronosticosPreview({
  overlays,
  onChange,
}: {
  overlays: PronosticosOverlaysConfig;
  onChange: (next: PronosticosOverlaysConfig) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ target: DragTarget; offset: number } | null>(null);
  const [activeTarget, setActiveTarget] = useState<DragTarget | null>(null);

  const updateY = useCallback(
    (target: DragTarget, clientY: number) => {
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const raw = (clientY - rect.top) / rect.height;
      const clamped = Math.max(0, Math.min(1, raw));
      onChange({ ...overlays, [target]: Number(clamped.toFixed(3)) });
    },
    [overlays, onChange],
  );

  function handlePointerDown(target: DragTarget) {
    return (e: React.PointerEvent) => {
      e.stopPropagation();
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      dragRef.current = { target, offset: 0 };
      setActiveTarget(target);
      updateY(target, e.clientY);
    };
  }
  function handlePointerMove(e: React.PointerEvent) {
    const d = dragRef.current;
    if (!d) return;
    updateY(d.target, e.clientY);
  }
  function handlePointerUp(e: React.PointerEvent) {
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    dragRef.current = null;
    setActiveTarget(null);
  }
  function handleDoubleClick(target: DragTarget) {
    return () => onChange({ ...overlays, [target]: RESET_VALUES[target] });
  }

  const teamShieldHeightPct = overlays.team_shield_height_pct;
  const teamShieldInsetPct = overlays.team_shield_x_inset_pct;
  const leagueLogoHeightPct = overlays.league_logo_height_pct;
  const profileHeightPct = overlays.profile_cta_height_pct;

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Previsualización 9:16 · arrastra para posicionar
      </p>
      <div
        ref={ref}
        className="relative w-full select-none overflow-hidden rounded-md border border-dashed border-muted-foreground/30 bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900"
        style={{ aspectRatio: "9 / 16", containerType: "inline-size" }}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {/* Zonas seguras TikTok */}
        <div className="pointer-events-none absolute inset-x-2 top-2 rounded border border-dashed border-amber-500/30 px-1 py-0.5 text-[8px] uppercase text-amber-500/80">
          UI top
        </div>
        <div className="pointer-events-none absolute inset-x-2 bottom-2 rounded border border-dashed border-amber-500/30 px-1 py-0.5 text-right text-[8px] uppercase text-amber-500/80">
          UI bottom
        </div>

        {/* Logos de ligas (intro) */}
        {overlays.add_league_overlay && (
          <DraggableRow
            top={overlays.league_overlay_y_pct}
            active={activeTarget === "league_overlay_y_pct"}
            onPointerDown={handlePointerDown("league_overlay_y_pct")}
            onDoubleClick={handleDoubleClick("league_overlay_y_pct")}
            label={`Ligas Y=${overlays.league_overlay_y_pct.toFixed(2)}`}
          >
            <div
              className="flex items-center justify-center gap-1.5"
              style={{ height: `${leagueLogoHeightPct * 100}cqh` }}
            >
              {["⚽", "🏆", "🥅"].map((emoji, i) => (
                <div
                  key={i}
                  className="flex aspect-square items-center justify-center rounded-full bg-blue-500/80 ring-2 ring-white/50 text-[3cqi]"
                  style={{ height: "100%" }}
                >
                  {emoji}
                </div>
              ))}
            </div>
          </DraggableRow>
        )}

        {/* Escudos de equipo (left + right) */}
        <DraggableRow
          top={overlays.team_shield_y_pct}
          active={activeTarget === "team_shield_y_pct"}
          onPointerDown={handlePointerDown("team_shield_y_pct")}
          onDoubleClick={handleDoubleClick("team_shield_y_pct")}
          label={`Escudos Y=${overlays.team_shield_y_pct.toFixed(2)}`}
        >
          <div
            className="relative w-full"
            style={{ height: `${teamShieldHeightPct * 100}cqh` }}
          >
            <div
              className="absolute flex aspect-square items-center justify-center rounded-md bg-rose-600/80 text-white shadow-md ring-2 ring-white/60"
              style={{
                left: `${teamShieldInsetPct * 100}cqi`,
                top: 0,
                height: "100%",
                fontSize: "3.5cqi",
                fontWeight: 700,
              }}
            >
              HOME
            </div>
            <div
              className="absolute flex aspect-square items-center justify-center rounded-md bg-cyan-600/80 text-white shadow-md ring-2 ring-white/60"
              style={{
                right: `${teamShieldInsetPct * 100}cqi`,
                top: 0,
                height: "100%",
                fontSize: "3.5cqi",
                fontWeight: 700,
              }}
            >
              AWAY
            </div>
          </div>
        </DraggableRow>

        {/* Perfil CTA (midroll) */}
        <DraggableRow
          top={overlays.profile_cta_y_pct}
          active={activeTarget === "profile_cta_y_pct"}
          onPointerDown={handlePointerDown("profile_cta_y_pct")}
          onDoubleClick={handleDoubleClick("profile_cta_y_pct")}
          label={`Perfil CTA Y=${overlays.profile_cta_y_pct.toFixed(2)}`}
        >
          <div
            className="mx-auto flex items-center justify-center rounded-2xl bg-fuchsia-500/70 text-white ring-2 ring-white/60"
            style={{
              height: `${profileHeightPct * 100}cqh`,
              width: `${profileHeightPct * 100 * 0.6}cqh`,
              fontSize: "3cqi",
              fontWeight: 700,
            }}
          >
            @perfil
          </div>
        </DraggableRow>

        {/* Subtítulos karaoke */}
        <DraggableRow
          top={overlays.subtitle_y_pct}
          active={activeTarget === "subtitle_y_pct"}
          onPointerDown={handlePointerDown("subtitle_y_pct")}
          onDoubleClick={handleDoubleClick("subtitle_y_pct")}
          label={`Subs Y=${overlays.subtitle_y_pct.toFixed(2)}`}
        >
          <div
            className="mx-auto inline-block rounded bg-black/40 px-2 py-0.5 text-center text-white"
            style={{ fontSize: "5cqi", fontWeight: 900 }}
          >
            <span className="rounded bg-rose-600 px-1.5 py-0.5">SUBS</span>{" "}
            karaoke
          </div>
        </DraggableRow>
      </div>

      <p className="text-[10px] text-muted-foreground">
        Arrastra cada elemento para ajustar su posición. Doble-click = reset a default.
      </p>
    </div>
  );
}

function DraggableRow({
  top,
  active,
  label,
  onPointerDown,
  onDoubleClick,
  children,
}: {
  top: number;
  active: boolean;
  label: string;
  onPointerDown: (e: React.PointerEvent) => void;
  onDoubleClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "group absolute inset-x-0 cursor-grab touch-none active:cursor-grabbing",
        active && "ring-2 ring-primary/60",
      )}
      style={{ top: `${top * 100}%`, transform: "translateY(-50%)" }}
      onPointerDown={onPointerDown}
      onDoubleClick={onDoubleClick}
    >
      {children}
      <div
        className={cn(
          "pointer-events-none absolute -left-1 top-1/2 -translate-y-1/2 rounded bg-primary/80 px-1 py-0.5 text-[8px] font-medium text-primary-foreground opacity-0 transition-opacity group-hover:opacity-100",
          active && "opacity-100",
        )}
      >
        {label}
      </div>
    </div>
  );
}
