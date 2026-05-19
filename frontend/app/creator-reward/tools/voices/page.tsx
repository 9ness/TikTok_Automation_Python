"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Mic, Pause, Play, Plus, RefreshCw, Trash2, Upload, Wrench } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  buildVoiceSampleUrl,
  useCloneVoice,
  useDeleteVoice,
  useSyncVoicesCatalog,
  useVoices,
  useVoicesSyncStatus,
} from "@/lib/queries/voices";
import type { Voice } from "@/lib/types/voice";

/**
 * Página global de gestión de voces — sirve como hub para:
 *  - Listar presets MiniMax (ES + EN) + voces clonadas en Redis
 *  - Audicionar cada voz con un sample MP3 cacheado server-side
 *  - Clonar nuevas voces (form: nombre + sample 10-30s MP3/WAV/M4A)
 *  - Borrar clones (presets son inmutables)
 *
 * Las voces aquí se ven inmediatamente en cualquier modo que use VoicePicker
 * (Construcción POV, futuras herramientas, etc.).
 */
type GenderFilter = "all" | "male" | "female" | "neutral";
type AgeFilter = "all" | "young" | "adult" | "mature";

export default function VoiceToolsPage() {
  const [lang, setLang] = useState<"all" | "en" | "es">("all");
  const [gender, setGender] = useState<GenderFilter>("all");
  const [age, setAge] = useState<AgeFilter>("all");
  const voices = useVoices({
    include_presets: true,
    language: lang === "all" ? undefined : lang,
    gender: gender === "all" ? undefined : gender,
    age_group: age === "all" ? undefined : age,
  });
  const clone = useCloneVoice();
  const del = useDeleteVoice();
  const sync = useSyncVoicesCatalog();
  const syncStatus = useVoicesSyncStatus();

  // Auto-sync silencioso si nunca se ha sincronizado (evita ver la lista
  // hardcoded ES-only durante la primera visita después del deploy).
  useEffect(() => {
    if (
      syncStatus.data &&
      !syncStatus.data.cached &&
      !sync.isPending &&
      !sync.isError
    ) {
      sync.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [syncStatus.data?.cached]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneName, setCloneName] = useState("");
  const [cloneLang, setCloneLang] = useState<"en" | "es">("en");
  const [cloneFile, setCloneFile] = useState<File | null>(null);

  const items = voices.data?.items ?? [];

  function togglePlay(voice: Voice) {
    const url = buildVoiceSampleUrl(voice.id);
    if (playing === voice.id) {
      audioRef.current?.pause();
      setPlaying(null);
      return;
    }
    audioRef.current?.pause();
    const audio = new Audio(url);
    audio.onended = () => setPlaying(null);
    audio.onerror = () => {
      toast.error("No se pudo cargar el sample.");
      setPlaying(null);
    };
    audio.play().catch(() => {
      toast.error("El navegador bloqueó la reproducción.");
      setPlaying(null);
    });
    audioRef.current = audio;
    setPlaying(voice.id);
  }

  async function submitClone() {
    if (!cloneFile || !cloneName.trim()) {
      toast.error("Pon un nombre y elige un archivo.");
      return;
    }
    try {
      const v = await clone.mutateAsync({
        file: cloneFile,
        name: cloneName.trim(),
        language: cloneLang,
      });
      toast.success(`Voz '${v.name}' clonada.`);
      setCloneOpen(false);
      setCloneName("");
      setCloneFile(null);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Error al clonar voz.");
    }
  }

  async function deleteClone(voice: Voice) {
    if (voice.is_preset) return;
    if (!confirm(`¿Borrar '${voice.name}'?`)) return;
    try {
      await del.mutateAsync(voice.id);
      toast.success("Voz borrada.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Error al borrar.");
    }
  }

  return (
    <div className="container mx-auto space-y-4 p-4 sm:p-6 md:p-8">
      <header className="flex flex-wrap items-center gap-3">
        <Wrench className="h-6 w-6 text-amber-500" />
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">Herramientas · Voces</h1>
          <p className="text-sm text-muted-foreground">
            Biblioteca global MiniMax — presets + clones reutilizables en todos
            los modos.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={lang} onValueChange={(v) => setLang(v as typeof lang)}>
            <SelectTrigger className="h-9 w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos los idiomas</SelectItem>
              <SelectItem value="en">Inglés</SelectItem>
              <SelectItem value="es">Español</SelectItem>
            </SelectContent>
          </Select>
          <Select value={gender} onValueChange={(v) => setGender(v as GenderFilter)}>
            <SelectTrigger className="h-9 w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos los géneros</SelectItem>
              <SelectItem value="male">Masculino</SelectItem>
              <SelectItem value="female">Femenino</SelectItem>
              <SelectItem value="neutral">Neutral</SelectItem>
            </SelectContent>
          </Select>
          <Select value={age} onValueChange={(v) => setAge(v as AgeFilter)}>
            <SelectTrigger className="h-9 w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas las edades</SelectItem>
              <SelectItem value="young">Joven / Niño</SelectItem>
              <SelectItem value="adult">Adulto</SelectItem>
              <SelectItem value="mature">Mayor</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            onClick={async () => {
              try {
                const res = await sync.mutateAsync();
                toast.success(`Catálogo MiniMax sincronizado · ${res.count} voces.`);
              } catch (e) {
                toast.error(`Sync falló: ${(e as Error).message}`);
              }
            }}
            disabled={sync.isPending}
            title="Refresca el catálogo system desde MiniMax (cache 24h)"
          >
            {sync.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Sincronizar
          </Button>
          <Button onClick={() => setCloneOpen(true)}>
            <Plus className="h-4 w-4" />
            Clonar voz
          </Button>
        </div>
      </header>
      {syncStatus.data?.cached && (
        <p className="text-xs text-muted-foreground">
          Catálogo MiniMax: {syncStatus.data.count} voces system ·
          actualizado hace {Math.round((syncStatus.data.age_seconds ?? 0) / 60)} min
          {syncStatus.data.age_seconds && syncStatus.data.age_seconds > 23 * 3600
            ? " (expira pronto — pulsa Sincronizar)"
            : ""}
        </p>
      )}
      {syncStatus.data && !syncStatus.data.cached && !sync.isPending && (
        <p className="text-xs text-amber-500">
          Catálogo aún no sincronizado. Pulsa &quot;Sincronizar&quot; para traer las voces reales de tu cuenta MiniMax.
        </p>
      )}

      {voices.isLoading ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No hay voces para este filtro.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((v) => (
            <Card key={v.id}>
              <CardContent className="space-y-2 p-4">
                <div className="flex items-start gap-2">
                  <Mic
                    className={`mt-0.5 h-4 w-4 shrink-0 ${
                      v.is_preset ? "text-muted-foreground" : "text-cyan-500"
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{v.name}</p>
                    <p className="truncate font-mono text-[10px] text-muted-foreground">
                      {v.minimax_voice_id}
                    </p>
                  </div>
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-muted-foreground">
                    {v.language}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1"
                    onClick={() => togglePlay(v)}
                  >
                    {playing === v.id ? (
                      <Pause className="h-3.5 w-3.5" />
                    ) : (
                      <Play className="h-3.5 w-3.5" />
                    )}
                    Audicionar
                  </Button>
                  {!v.is_preset && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-destructive"
                      onClick={() => deleteClone(v)}
                      disabled={del.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={cloneOpen} onOpenChange={setCloneOpen}>
        <DialogContent className="w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Clonar nueva voz</DialogTitle>
            <DialogDescription>
              Sample limpio de 10–30s (MP3/WAV/M4A), sin música. MiniMax devuelve
              un voice_id reutilizable.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="vt-name" className="text-xs">Nombre</Label>
              <Input
                id="vt-name"
                value={cloneName}
                onChange={(e) => setCloneName(e.target.value)}
                placeholder="Ej. Narrador POV 1"
                maxLength={80}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Idioma</Label>
              <Select value={cloneLang} onValueChange={(v) => setCloneLang(v as "en" | "es")}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">Inglés</SelectItem>
                  <SelectItem value="es">Español</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Sample de audio</Label>
              {cloneFile ? (
                <div className="flex items-center gap-2 rounded-md border bg-card/50 p-2 text-sm">
                  <Mic className="h-4 w-4 text-muted-foreground" />
                  <span className="flex-1 truncate">{cloneFile.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {(cloneFile.size / 1024).toFixed(0)} KB
                  </span>
                  <Button size="icon" variant="ghost" onClick={() => setCloneFile(null)}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ) : (
                <label
                  htmlFor="vt-audio"
                  className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed py-6 text-sm text-muted-foreground transition-colors hover:bg-accent"
                >
                  <Upload className="h-4 w-4" />
                  <span>Click para subir (.mp3 / .wav / .m4a)</span>
                  <input
                    id="vt-audio"
                    type="file"
                    accept=".mp3,.wav,.m4a,audio/mpeg,audio/wav,audio/x-m4a"
                    className="sr-only"
                    onChange={(e) => setCloneFile(e.target.files?.[0] ?? null)}
                  />
                </label>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCloneOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={submitClone} disabled={clone.isPending}>
              {clone.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Clonar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
