"use client";

import { useState } from "react";
import { Image as ImageIcon, Loader2, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import {
  matchPhotoFileUrl,
  useDeleteMatchPhoto,
  useMatchPhotoFolders,
  useMatchPhotos,
  useSaveMatchPhoto,
  useSearchMatchPhotos,
} from "@/lib/queries/creator-reward/matchPhotos";

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
