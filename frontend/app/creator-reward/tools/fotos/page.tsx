"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Image as ImageIcon,
  Loader2,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import {
  matchPhotoFileUrl,
  matchPhotosKeys,
  useAutoFetchMatchPhoto,
  useDeleteMatchPhoto,
  useMatchPhotoFolders,
  useMatchPhotos,
  useMatchTeamsForDate,
  useSaveMatchPhoto,
  useSearchMatchPhotos,
} from "@/lib/queries/creator-reward/matchPhotos";

function defaultDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

export default function MatchPhotosPage() {
  const [team, setTeam] = useState("");
  const [query, setQuery] = useState("");
  const [savingUrl, setSavingUrl] = useState<string | null>(null);

  const folders = useMatchPhotoFolders();
  const search = useSearchMatchPhotos();
  const save = useSaveMatchPhoto();
  const del = useDeleteMatchPhoto();
  const teamTrim = team.trim();
  const saved = useMatchPhotos(teamTrim || null);

  const results = search.data?.images ?? [];

  // Auto-búsqueda por jornada (una foto de jugador por equipo de la fecha).
  const qc = useQueryClient();
  const [dateInput, setDateInput] = useState(defaultDate());
  const [activeDate, setActiveDate] = useState<string | null>(null);
  const teamsQ = useMatchTeamsForDate(activeDate);
  const autoFetch = useAutoFetchMatchPhoto();
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number; current: string } | null>(null);
  const [teamLog, setTeamLog] = useState<Record<string, string>>({});

  async function runAutoFetch(mode: "missing" | "all") {
    const teams = teamsQ.data?.teams ?? [];
    const targets = mode === "missing" ? teams.filter((t) => !t.has_photos) : teams;
    if (targets.length === 0) {
      toast.info(
        mode === "missing"
          ? "Todos los equipos ya tienen foto."
          : "No hay equipos en esta fecha.",
      );
      return;
    }
    setRunning(true);
    setTeamLog({});
    let created = 0;
    for (let i = 0; i < targets.length; i++) {
      const t = targets[i];
      if (!t) continue;
      setProgress({ done: i, total: targets.length, current: t.name });
      try {
        const res = await autoFetch.mutateAsync({ team: t.name, mode });
        const label =
          res.status === "created"
            ? "✅ guardada"
            : res.status === "exists"
              ? "• ya tenía"
              : res.status === "no_good"
                ? "⚠️ sin jugador"
                : "✗ error";
        setTeamLog((p) => ({ ...p, [t.name]: label }));
        if (res.status === "created") created++;
      } catch {
        setTeamLog((p) => ({ ...p, [t.name]: "✗ error" }));
      }
    }
    setProgress(null);
    setRunning(false);
    toast.success(`Auto-búsqueda terminada: ${created} foto(s) nueva(s).`);
    qc.invalidateQueries({ queryKey: matchPhotosKeys.folders() });
    qc.invalidateQueries({ queryKey: matchPhotosKeys.teamsForDate(activeDate ?? "") });
    if (teamTrim) qc.invalidateQueries({ queryKey: matchPhotosKeys.team(teamTrim) });
  }

  async function runSearch() {
    const q = query.trim();
    if (!q) {
      toast.error("Escribe qué buscar (ej. 'Lamine Yamal celebración').");
      return;
    }
    try {
      await search.mutateAsync({ query: q, limit: 40 });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Error en la búsqueda.");
    }
  }

  async function savePhoto(imageUrl: string) {
    if (!teamTrim) {
      toast.error("Primero indica el equipo (arriba) donde guardar la foto.");
      return;
    }
    setSavingUrl(imageUrl);
    try {
      const res = await save.mutateAsync({ image_url: imageUrl, team: teamTrim });
      toast.success(`Guardada en ${res.team} (${res.filename}).`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo guardar.");
    } finally {
      setSavingUrl(null);
    }
  }

  async function deletePhoto(filename: string) {
    try {
      await del.mutateAsync({ team: teamTrim, filename });
      toast.success("Foto borrada.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo borrar.");
    }
  }

  return (
    <div className="container mx-auto space-y-4 p-4 sm:p-6 md:p-8">
      <header className="flex flex-wrap items-center gap-3">
        <ImageIcon className="h-6 w-6 text-sky-500" />
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">
            Herramientas · Fotos de partido
          </h1>
          <p className="text-sm text-muted-foreground">
            Busca fotos (Bing) y guárdalas en 9:16 dentro de la carpeta del equipo
            para los vídeos V2 (viral).
          </p>
        </div>
      </header>

      {/* Auto-búsqueda por jornada */}
      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-amber-500" />
            <span className="text-sm font-semibold">Auto-buscar por jornada</span>
          </div>
          <p className="text-xs text-muted-foreground">
            Carga los equipos de los partidos de una fecha y busca una foto de
            jugador (filtrada con IA) por equipo. 9:16 automático.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <Input
              type="date"
              value={dateInput}
              onChange={(e) => setDateInput(e.target.value)}
              className="h-9 w-44"
            />
            <Button
              variant="outline"
              className="h-9"
              onClick={() => setActiveDate(dateInput)}
              disabled={teamsQ.isFetching}
            >
              {teamsQ.isFetching ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                "Cargar equipos"
              )}
            </Button>
            <Button
              className="h-9"
              onClick={() => runAutoFetch("missing")}
              disabled={running || !teamsQ.data?.teams.length}
            >
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              <span className="ml-1">Buscar las que faltan</span>
            </Button>
            <Button
              variant="secondary"
              className="h-9"
              onClick={() => runAutoFetch("all")}
              disabled={running || !teamsQ.data?.teams.length}
            >
              Buscar todas (+1)
            </Button>
          </div>

          {progress && (
            <p className="text-xs text-muted-foreground">
              Buscando {progress.done + 1}/{progress.total}: {progress.current}…
            </p>
          )}

          {activeDate && teamsQ.data && (
            <div className="flex flex-wrap gap-1.5">
              {teamsQ.data.teams.length === 0 && (
                <span className="text-xs text-muted-foreground">
                  No hay partidos/equipos para {activeDate}.
                </span>
              )}
              {teamsQ.data.teams.map((t) => (
                <span
                  key={t.name}
                  className={`rounded-full border px-2 py-0.5 text-[11px] ${
                    t.has_photos
                      ? "border-emerald-500/40 bg-emerald-500/10"
                      : "border-border"
                  }`}
                  title={teamLog[t.name] ?? (t.has_photos ? `${t.count} foto(s)` : "sin foto")}
                >
                  {t.has_photos ? "✓" : "○"} {t.name}
                  {teamLog[t.name] ? ` · ${teamLog[t.name]}` : ""}
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Equipo destino */}
      <Card>
        <CardContent className="space-y-2 p-4">
          <Label className="text-xs">Equipo / carpeta destino</Label>
          <Input
            list="fotos-folders"
            value={team}
            onChange={(e) => setTeam(e.target.value)}
            placeholder="Ej. Real Madrid (elige una existente o escribe una nueva)"
            className="h-9 max-w-md"
          />
          <datalist id="fotos-folders">
            {folders.data?.folders.map((f) => (
              <option key={f.name} value={f.name}>
                {f.name} ({f.count})
              </option>
            ))}
          </datalist>
          <p className="text-xs text-muted-foreground">
            Se guarda en{" "}
            <code>BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/{teamTrim || "<equipo>"}/</code>
            {folders.data?.folders.length
              ? ` · ${folders.data.folders.length} carpetas con fotos`
              : ""}
          </p>
        </CardContent>
      </Card>

      {/* Buscador */}
      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Buscar fotos</Label>
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && runSearch()}
                placeholder="Ej. Lamine Yamal celebración, estadio Bernabéu…"
                className="h-9"
              />
            </div>
            <Button onClick={runSearch} disabled={search.isPending} className="h-9">
              {search.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              <span className="ml-1">Buscar</span>
            </Button>
          </div>

          {results.length > 0 && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {results.map((img) => {
                const isSaving = savingUrl === img.url;
                return (
                  <div
                    key={img.url}
                    className="group relative overflow-hidden rounded-md border bg-muted/30"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={img.thumbnail}
                      alt={img.title}
                      className="aspect-[3/4] w-full object-cover"
                      loading="lazy"
                    />
                    <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-1 bg-black/60 p-1">
                      <span className="truncate text-[10px] text-white/80">
                        {img.width && img.height ? `${img.width}×${img.height}` : "—"}
                      </span>
                      <Button
                        size="sm"
                        className="h-6 px-2 text-[11px]"
                        onClick={() => savePhoto(img.url)}
                        disabled={isSaving}
                      >
                        {isSaving ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          "Guardar"
                        )}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          {search.isSuccess && results.length === 0 && (
            <p className="text-sm text-muted-foreground">Sin resultados.</p>
          )}
        </CardContent>
      </Card>

      {/* Galería guardada del equipo */}
      {teamTrim && (
        <Card>
          <CardContent className="space-y-3 p-4">
            <Label className="text-xs">
              Guardadas en {teamTrim}
              {saved.data ? ` (${saved.data.photos.length})` : ""}
            </Label>
            {saved.isLoading && (
              <p className="text-sm text-muted-foreground">Cargando…</p>
            )}
            {saved.data && saved.data.photos.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Aún no hay fotos para este equipo.
              </p>
            )}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {saved.data?.photos.map((p) => (
                <div
                  key={p.filename}
                  className="group relative overflow-hidden rounded-md border"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={matchPhotoFileUrl(p.url)}
                    alt={p.filename}
                    className="aspect-[9/16] w-full object-cover"
                    loading="lazy"
                  />
                  <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-black/60 p-1">
                    <span className="truncate text-[10px] text-white/80">
                      {p.size_kb} KB
                    </span>
                    <Button
                      size="sm"
                      variant="destructive"
                      className="h-6 w-6 p-0"
                      onClick={() => deletePhoto(p.filename)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
