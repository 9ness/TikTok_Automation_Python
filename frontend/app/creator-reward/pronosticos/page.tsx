"use client";

import { useEffect, useRef, useState } from "react";
import { Calendar, Loader2, Pause, Play, Send } from "lucide-react";
import { toast } from "sonner";

import { PronosticosPreview } from "@/components/creator-reward/pronosticos/PronosticosPreview";
import { VersionsList } from "@/components/creator-reward/pronosticos/VersionsList";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CollapsibleCard } from "@/components/ui/collapsible-card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { ApiError } from "@/lib/api";
import { useLocalStorageState } from "@/lib/hooks/useLocalStorageState";
import {
  useEnqueuePronosticos,
  useLatestPronosticosDate,
  usePronosticosVersions,
} from "@/lib/queries/creator-reward/pronosticos";
import { buildVoiceSampleUrl } from "@/lib/queries/voices";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type {
  PronosticosAudioConfig,
  PronosticosOverlaysConfig,
} from "@/lib/types/creator-reward";

// Voces favoritas — mismas que el Streamlit original (FAVORITE_VOICES).
const FAVORITE_VOICES = [
  { id: "Spanish_Strong-WilledBoy", label: "💪 Strong-Willed Boy" },
  { id: "Spanish_EnergeticBoy", label: "⚡ Energetic Boy" },
  { id: "Spanish_PassionateWarrior", label: "🔥 Passionate Warrior" },
] as const;

const RESOLUTIONS: Array<{ label: string; size: [number, number] }> = [
  { label: "1080p (Lento)", size: [1080, 1920] },
  { label: "720p (Medio)", size: [720, 1280] },
  { label: "480p (Rápido)", size: [480, 854] },
  { label: "240p (Ultra Rápido)", size: [240, 426] },
];

const DEFAULT_AUDIO: PronosticosAudioConfig = {
  add_subtitles: true,
  add_money_sfx: true,
  sfx_volume: 0.5,
  add_clink_sfx: true,
  clink_volume: 0.4,
  add_camera_sfx: true,
  camera_volume: 0.5,
  add_background_music: true,
  bgm_volume: 0.2,
};

const DEFAULT_OVERLAYS: PronosticosOverlaysConfig = {
  use_intro_folder: true,
  add_league_overlay: true,
  league_overlay_duration: 2.5,
  saturation: 1.25,
  show_pick_carousel: false,
  video_style: "standard",
  // Defaults históricos del pipeline (pronosticos/pipeline.py).
  subtitle_y_pct: 0.78,
  league_overlay_y_pct: 0.30,
  league_logo_height_pct: 0.13,
  team_shield_y_pct: 0.43,
  team_shield_height_pct: 0.22,
  team_shield_x_inset_pct: 0.06,
  profile_cta_y_pct: 0.36,
  profile_cta_height_pct: 0.32,
};

function isoToday(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

export default function PronosticosPage() {
  const openQueue = useDrawerStore((s) => s.openQueue);
  const enqueue = useEnqueuePronosticos();
  const latestDate = useLatestPronosticosDate();

  const [date, setDate] = useState<string>(isoToday());
  const versions = usePronosticosVersions(date);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [scriptOverrides, setScriptOverrides] = useState<Record<string, string>>(
    {},
  );

  // Persistencia de preferencias del usuario
  const [voiceId, setVoiceId] = useLocalStorageState<string>(
    "pronosticos.voice.v1",
    FAVORITE_VOICES[0].id,
  );
  const [voiceCustom, setVoiceCustom] = useLocalStorageState<string>(
    "pronosticos.voice_custom.v1",
    "",
  );
  const [resolutionIdx, setResolutionIdx] = useLocalStorageState<number>(
    "pronosticos.resolution_idx.v1",
    0,
  );
  const [publishToRedis, setPublishToRedis] = useLocalStorageState<boolean>(
    "pronosticos.publish_redis.v1",
    false,
  );
  const [audio, setAudio] = useLocalStorageState<PronosticosAudioConfig>(
    "pronosticos.audio.v1",
    DEFAULT_AUDIO,
  );
  const [overlays, setOverlays] = useLocalStorageState<PronosticosOverlaysConfig>(
    "pronosticos.overlays.v1",
    DEFAULT_OVERLAYS,
  );

  // V2 = estilo "viral": solo voz, 9:16 fijo, sin subtítulos ni posiciones.
  const isViral = overlays.video_style === "viral";

  // Preview de voz — reproduce la muestra MP3 cacheada del endpoint /voices/{id}/sample.
  const [playingVoice, setPlayingVoice] = useState<string | null>(null);
  const previewRef = useRef<HTMLAudioElement | null>(null);
  function previewVoice() {
    const vid = voiceId === "__custom__" ? voiceCustom.trim() : voiceId;
    if (!vid) {
      toast.error("Elige una voz o escribe un voice ID primero.");
      return;
    }
    if (previewRef.current) {
      previewRef.current.pause();
      previewRef.current = null;
    }
    if (playingVoice === vid) {
      setPlayingVoice(null);
      return;
    }
    const a = new Audio(buildVoiceSampleUrl(vid));
    previewRef.current = a;
    setPlayingVoice(vid);
    a.onended = () => setPlayingVoice(null);
    a.onerror = () => {
      toast.error("No se pudo cargar la muestra de esa voz.");
      setPlayingVoice(null);
    };
    a.play().catch(() => {
      toast.error("No se pudo reproducir la muestra.");
      setPlayingVoice(null);
    });
  }
  useEffect(() => {
    return () => {
      previewRef.current?.pause();
    };
  }, []);

  // Auto pre-select la versión `is_selected` cuando carga
  useEffect(() => {
    if (versions.data?.versions) {
      const auto = versions.data.versions.find((v) => v.is_selected);
      if (auto) setSelectedIds(new Set([auto.id]));
    }
  }, [versions.data]);

  function toggle(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function loadLatest() {
    if (latestDate.data?.latest_date) {
      setDate(latestDate.data.latest_date);
      toast.success(`Cargada fecha ${latestDate.data.latest_date}`);
    } else {
      toast.error("No se encontró ninguna fecha disponible en los últimos 14 días.");
    }
  }

  async function submit() {
    if (selectedIds.size === 0) return;
    const overridesObj: Record<string, string> = {};
    if (versions.data) {
      for (const v of versions.data.versions) {
        if (selectedIds.has(v.id)) {
          const edited = scriptOverrides[v.id];
          if (edited !== undefined && edited.trim() !== v.script.trim()) {
            overridesObj[v.id] = edited;
          }
        }
      }
    }
    const finalVoice =
      voiceId === "__custom__" ? voiceCustom.trim() || null : voiceId || null;

    // En V2 (viral): 9:16 fijo y perfil de audio limpio (sin subtítulos ni
    // clink/dinero/cámara — el flash de transición ya va automático). El resto
    // de posiciones/overlays no aplican (el pipeline las ignora en viral).
    const videoSize: [number, number] = isViral
      ? [1080, 1920]
      : RESOLUTIONS[resolutionIdx]?.size ?? [1080, 1920];
    const effectiveAudio: PronosticosAudioConfig = isViral
      ? {
          ...audio,
          add_subtitles: false,
          add_money_sfx: false,
          add_clink_sfx: false,
          add_camera_sfx: false,
        }
      : audio;

    try {
      const res = await enqueue.mutateAsync({
        target_date: date,
        version_ids: Array.from(selectedIds),
        voice_id_override: finalVoice,
        script_overrides: overridesObj,
        video_size: videoSize,
        publish_to_redis: publishToRedis,
        audio: effectiveAudio,
        overlays,
      });
      toast.success(`${res.total_enqueued} versión(es) encoladas.`);
      openQueue();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al encolar.");
    }
  }

  // Resumen para subtitles de los CollapsibleCards
  const audioSummary = (() => {
    const sfx = [
      audio.add_money_sfx && "money",
      audio.add_clink_sfx && "clink",
      audio.add_camera_sfx && "camera",
    ].filter(Boolean);
    const sfxLabel = sfx.length > 0 ? `${sfx.length} SFX` : "sin SFX";
    return `${audio.add_subtitles ? "subs" : "no subs"} · ${sfxLabel} · BGM ${audio.add_background_music ? `${Math.round(audio.bgm_volume * 100)}%` : "off"}`;
  })();
  const overlaysSummary = `${overlays.video_style === "viral" ? "🔥 viral" : "clásico"} · intro ${overlays.use_intro_folder ? "✓" : "✗"} · ligas ${overlays.add_league_overlay ? "✓" : "✗"} · sat ${overlays.saturation.toFixed(2)} · carrusel ${overlays.show_pick_carousel ? "✓" : "✗"}`;
  const voiceSummary =
    voiceId === "__custom__"
      ? voiceCustom || "Custom (vacío)"
      : FAVORITE_VOICES.find((v) => v.id === voiceId)?.label ?? voiceId;

  return (
    <div className="container mx-auto space-y-4 p-6 md:p-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Pronósticos Diarios</h1>
        <p className="text-sm text-muted-foreground">
          Carga el guion de Redis (<code>bet-ai-master</code>) y encola TTS+render.
        </p>
      </header>

      {/* Fecha + cargar última */}
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-3">
          <div className="space-y-1">
            <Label className="text-xs">Fecha objetivo</Label>
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <Input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="h-9 w-44"
              />
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={loadLatest}
            disabled={latestDate.isLoading}
          >
            Cargar última disponible
          </Button>
        </CardContent>
      </Card>

      {/* Selector principal de versión/estilo del vídeo */}
      <Card>
        <CardContent className="p-3">
          <Label className="text-xs">Versión del vídeo</Label>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setOverlays({ ...overlays, video_style: "standard" })}
              className={`rounded-lg border p-3 text-left transition ${
                !isViral
                  ? "border-primary bg-primary/10"
                  : "border-border hover:bg-muted/50"
              }`}
            >
              <div className="text-sm font-semibold">V1 · Estándar</div>
              <div className="text-xs text-muted-foreground">
                Versión clásica con todas las opciones (posiciones, subtítulos,
                overlays, SFX).
              </div>
            </button>
            <button
              type="button"
              onClick={() => setOverlays({ ...overlays, video_style: "viral" })}
              className={`rounded-lg border p-3 text-left transition ${
                isViral
                  ? "border-primary bg-primary/10"
                  : "border-border hover:bg-muted/50"
              }`}
            >
              <div className="text-sm font-semibold">🔥 V2 · Viral</div>
              <div className="text-xs text-muted-foreground">
                Gancho + barra de partidos. Solo eliges la voz; 9:16 y posiciones
                fijas.
              </div>
            </button>
          </div>
        </CardContent>
      </Card>

      {versions.isLoading && <Skeleton className="h-40 w-full" />}

      {versions.data && !versions.data.payload_exists && (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No hay payload en Redis para {date}. Espera al cron de bet-ai-master
            (~18:05 hora Madrid) o usa &quot;Cargar última disponible&quot;.
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
        <div className="min-w-0 space-y-4">
          {versions.data?.payload_exists && (
            <VersionsList
              versions={versions.data.versions}
              selectedIds={selectedIds}
              onToggle={toggle}
              scriptOverrides={scriptOverrides}
              onScriptChange={(id, text) =>
                setScriptOverrides((prev) => ({ ...prev, [id]: text }))
              }
            />
          )}

          <CollapsibleCard
            title={isViral ? "Voz" : "Voz + Resolución"}
            subtitle={
              isViral
                ? `${voiceSummary} · 9:16`
                : `${voiceSummary} · ${RESOLUTIONS[resolutionIdx]?.label ?? "1080p"}`
            }
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs">Voz MiniMax</Label>
                <div className="flex items-center gap-2">
                  <Select value={voiceId} onValueChange={setVoiceId}>
                    <SelectTrigger className="h-9 flex-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FAVORITE_VOICES.map((v) => (
                        <SelectItem key={v.id} value={v.id}>
                          {v.label}
                        </SelectItem>
                      ))}
                      <SelectItem value="__custom__">✏️ Custom (voice ID)</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-9 shrink-0"
                    onClick={previewVoice}
                    title="Escuchar una frase con esta voz"
                  >
                    {playingVoice ? (
                      <Pause className="h-4 w-4" />
                    ) : (
                      <Play className="h-4 w-4" />
                    )}
                    <span className="ml-1">Probar</span>
                  </Button>
                </div>
              </div>
              {voiceId === "__custom__" && (
                <div className="space-y-1">
                  <Label className="text-xs">Voice ID personalizado</Label>
                  <Input
                    value={voiceCustom}
                    onChange={(e) => setVoiceCustom(e.target.value)}
                    placeholder="Spanish_..."
                    className="h-9 font-mono text-xs"
                  />
                </div>
              )}
              {!isViral && (
                <div className="space-y-1">
                  <Label className="text-xs">Resolución</Label>
                  <Select
                    value={String(resolutionIdx)}
                    onValueChange={(v) => setResolutionIdx(Number(v))}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {RESOLUTIONS.map((r, i) => (
                        <SelectItem key={r.label} value={String(i)}>
                          {r.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <label className="flex items-end gap-2 pb-1 text-sm">
                <Switch
                  checked={publishToRedis}
                  onCheckedChange={setPublishToRedis}
                />
                <span>Publicar URL del MP4 en Redis</span>
              </label>
            </div>
            {isViral && (
              <p className="mt-2 text-xs text-muted-foreground">
                V2 Viral: resolución 9:16 fija, sin subtítulos, posiciones de
                overlays predefinidas. Solo configuras la voz.
              </p>
            )}
          </CollapsibleCard>

          {!isViral && (
          <>
          <CollapsibleCard title="Audio (subs + SFX + BGM)" subtitle={audioSummary}>
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm font-medium">
                <Switch
                  checked={audio.add_subtitles}
                  onCheckedChange={(v) => setAudio({ ...audio, add_subtitles: v })}
                />
                Subtítulos karaoke
              </label>

              <SfxRow
                label="💰 Money SFX"
                enabled={audio.add_money_sfx}
                volume={audio.sfx_volume}
                volMin={0.2}
                volMax={1.0}
                onEnabled={(v) => setAudio({ ...audio, add_money_sfx: v })}
                onVolume={(v) => setAudio({ ...audio, sfx_volume: v })}
              />
              <SfxRow
                label="🥂 Clink SFX (1 por pick)"
                enabled={audio.add_clink_sfx}
                volume={audio.clink_volume}
                volMin={0.1}
                volMax={0.8}
                onEnabled={(v) => setAudio({ ...audio, add_clink_sfx: v })}
                onVolume={(v) => setAudio({ ...audio, clink_volume: v })}
              />
              <SfxRow
                label="📸 Camera SFX (perfil + ligas)"
                enabled={audio.add_camera_sfx}
                volume={audio.camera_volume}
                volMin={0.2}
                volMax={1.0}
                onEnabled={(v) => setAudio({ ...audio, add_camera_sfx: v })}
                onVolume={(v) => setAudio({ ...audio, camera_volume: v })}
              />
              <SfxRow
                label="🎵 Música de fondo"
                enabled={audio.add_background_music}
                volume={audio.bgm_volume}
                volMin={0.05}
                volMax={0.5}
                onEnabled={(v) =>
                  setAudio({ ...audio, add_background_music: v })
                }
                onVolume={(v) => setAudio({ ...audio, bgm_volume: v })}
              />
            </div>
          </CollapsibleCard>

          <CollapsibleCard title="Overlays + Vídeo" subtitle={overlaysSummary}>
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm">
                <Switch
                  checked={overlays.use_intro_folder}
                  onCheckedChange={(v) =>
                    setOverlays({ ...overlays, use_intro_folder: v })
                  }
                />
                <span>Usar BIBLIOTECA_INTRO/</span>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <Switch
                  checked={overlays.show_pick_carousel}
                  onCheckedChange={(v) =>
                    setOverlays({ ...overlays, show_pick_carousel: v })
                  }
                />
                <span>Carrusel de picks (experimental)</span>
              </label>
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm">
                  <Switch
                    checked={overlays.add_league_overlay}
                    onCheckedChange={(v) =>
                      setOverlays({ ...overlays, add_league_overlay: v })
                    }
                  />
                  <span>Overlay logos de ligas (en intro)</span>
                </label>
                {overlays.add_league_overlay && (
                  <SliderRow
                    label={`Duración: ${overlays.league_overlay_duration.toFixed(1)}s`}
                    value={overlays.league_overlay_duration}
                    min={1.5}
                    max={5.0}
                    step={0.1}
                    onChange={(v) =>
                      setOverlays({ ...overlays, league_overlay_duration: v })
                    }
                  />
                )}
              </div>
              <SliderRow
                label={`Saturación post-render: ${overlays.saturation.toFixed(2)}`}
                value={overlays.saturation}
                min={1.0}
                max={1.6}
                step={0.05}
                onChange={(v) => setOverlays({ ...overlays, saturation: v })}
              />
            </div>
          </CollapsibleCard>
          </>
          )}
        </div>

        {/* Sticky right column — preview + resumen + encolar */}
        <div className="space-y-3 lg:sticky lg:top-6">
          {!isViral && (
            <PronosticosPreview overlays={overlays} onChange={setOverlays} />
          )}
          <Card>
            <CardContent className="space-y-2 p-3 text-xs">
              <p className="font-semibold uppercase tracking-wider text-muted-foreground">
                Resumen
              </p>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Fecha</span>
                <span className="font-mono">{date}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Seleccionadas</span>
                <span className="font-semibold">{selectedIds.size}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Voz</span>
                <span className="truncate" title={voiceSummary}>
                  {voiceSummary}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Resolución</span>
                <span>{RESOLUTIONS[resolutionIdx]?.label}</span>
              </div>
            </CardContent>
          </Card>
          <Button
            onClick={submit}
            disabled={selectedIds.size === 0 || enqueue.isPending}
            size="lg"
            className="w-full"
          >
            {enqueue.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Encolar {selectedIds.size} versión{selectedIds.size === 1 ? "" : "es"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function SfxRow({
  label,
  enabled,
  volume,
  volMin,
  volMax,
  onEnabled,
  onVolume,
}: {
  label: string;
  enabled: boolean;
  volume: number;
  volMin: number;
  volMax: number;
  onEnabled: (v: boolean) => void;
  onVolume: (v: number) => void;
}) {
  return (
    <div className="space-y-1 rounded-md border bg-card/50 p-2">
      <label className="flex items-center justify-between gap-2 text-sm">
        <span className="flex items-center gap-2">
          <Switch checked={enabled} onCheckedChange={onEnabled} />
          {label}
        </span>
        <span className="font-mono text-xs text-muted-foreground">
          {Math.round(volume * 100)}%
        </span>
      </label>
      {enabled && (
        <input
          type="range"
          min={volMin}
          max={volMax}
          step={0.05}
          value={volume}
          onChange={(e) => onVolume(Number(e.target.value))}
          className="w-full"
        />
      )}
    </div>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full"
      />
    </div>
  );
}
