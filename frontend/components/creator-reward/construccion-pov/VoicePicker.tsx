"use client";

import { useMemo, useRef, useState } from "react";
import { Loader2, Mic, Pause, Play, Plus, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
  useVoices,
} from "@/lib/queries/voices";
import type { Voice } from "@/lib/types/voice";

/**
 * Selector de voz MiniMax con clonado integrado.
 *
 * - Filtra por language (default "en" para Construcción POV)
 * - Botón ▶︎ → reproduce un sample MP3 cacheado por el backend
 * - Botón "Clonar nueva voz" → modal con form (nombre + sample mp3/wav)
 * - Tras clonar se invalida la cache de voces y la nueva entra automáticamente
 */
export function VoicePicker({
  value,
  onChange,
  language = "en",
}: {
  value: string;
  onChange: (voiceId: string, voice: Voice) => void;
  language?: "en" | "es";
}) {
  const voices = useVoices({ language, include_presets: true });
  const clone = useCloneVoice();
  const del = useDeleteVoice();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneName, setCloneName] = useState("");
  const [cloneFile, setCloneFile] = useState<File | null>(null);

  const items = voices.data?.items ?? [];
  const selected = useMemo(
    () => items.find((v) => v.id === value) ?? null,
    [items, value],
  );

  // Auto-seleccionar la primera voz disponible si no hay nada seleccionado y
  // ya se cargó la lista.
  if (!value && items.length > 0) {
    onChange(items[0]!.id, items[0]!);
  }

  function togglePlay(voice: Voice) {
    const url = buildVoiceSampleUrl(voice.id);
    if (playing === voice.id) {
      audioRef.current?.pause();
      setPlaying(null);
      return;
    }
    if (audioRef.current) {
      audioRef.current.pause();
    }
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
      toast.error("Pon un nombre y elige un archivo de audio.");
      return;
    }
    try {
      const voice = await clone.mutateAsync({
        file: cloneFile,
        name: cloneName.trim(),
        language,
      });
      toast.success(`Voz '${voice.name}' clonada.`);
      onChange(voice.id, voice);
      setCloneOpen(false);
      setCloneName("");
      setCloneFile(null);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Error al clonar voz.");
    }
  }

  async function deleteClone(voice: Voice) {
    if (voice.is_preset) return;
    if (!confirm(`¿Borrar la voz '${voice.name}'? Esto no se puede deshacer.`)) return;
    try {
      await del.mutateAsync(voice.id);
      if (value === voice.id) onChange("", voice);
      toast.success("Voz borrada.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Error al borrar.");
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <Label className="text-xs">Voz narrada (MiniMax, {language.toUpperCase()})</Label>
          <Select
            value={value}
            onValueChange={(v) => {
              const voice = items.find((it) => it.id === v);
              if (voice) onChange(v, voice);
            }}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder={voices.isLoading ? "Cargando voces…" : "Elige voz"} />
            </SelectTrigger>
            <SelectContent>
              {items.map((v) => (
                <SelectItem key={v.id} value={v.id}>
                  <span className="flex items-center gap-2">
                    {v.is_preset ? (
                      <span className="text-[9px] uppercase tracking-wider text-muted-foreground">
                        preset
                      </span>
                    ) : (
                      <Mic className="h-3 w-3 text-cyan-500" />
                    )}
                    <span className="truncate">{v.name}</span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {selected && (
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="mt-5 h-9 w-9 shrink-0"
            onClick={() => togglePlay(selected)}
            aria-label="Reproducir sample"
          >
            {playing === selected.id ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
          </Button>
        )}
        <Button
          type="button"
          size="icon"
          variant="outline"
          className="mt-5 h-9 w-9 shrink-0"
          onClick={() => setCloneOpen(true)}
          aria-label="Clonar voz"
          title="Clonar nueva voz"
        >
          <Plus className="h-4 w-4" />
        </Button>
        {selected && !selected.is_preset && (
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="mt-5 h-9 w-9 shrink-0 text-destructive"
            onClick={() => deleteClone(selected)}
            aria-label="Borrar voz"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
      {selected && (
        <p className="text-[10px] text-muted-foreground">
          ID: <span className="font-mono">{selected.minimax_voice_id}</span>
        </p>
      )}

      <Dialog open={cloneOpen} onOpenChange={setCloneOpen}>
        <DialogContent className="w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Clonar nueva voz</DialogTitle>
            <DialogDescription>
              Sube un sample limpio de 10–30s (MP3/WAV/M4A) sin música. MiniMax
              creará un <span className="font-mono">voice_id</span> reutilizable.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="clone-name" className="text-xs">
                Nombre
              </Label>
              <Input
                id="clone-name"
                value={cloneName}
                onChange={(e) => setCloneName(e.target.value)}
                placeholder="Ej. Narrador POV 1"
                maxLength={80}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Sample de audio</Label>
              {cloneFile ? (
                <div className="flex items-center gap-2 rounded-md border bg-card/50 p-2 text-sm">
                  <Mic className="h-4 w-4 text-muted-foreground" />
                  <span className="truncate flex-1">{cloneFile.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {(cloneFile.size / 1024).toFixed(0)} KB
                  </span>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => setCloneFile(null)}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ) : (
                <label
                  htmlFor="clone-audio"
                  className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed py-6 text-sm text-muted-foreground transition-colors hover:bg-accent"
                >
                  <Upload className="h-4 w-4" />
                  <span>Click para subir (.mp3 / .wav / .m4a)</span>
                  <input
                    id="clone-audio"
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
