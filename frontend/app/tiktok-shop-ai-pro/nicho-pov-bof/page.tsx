"use client";

import {
  Check,
  ChevronLeft,
  ChevronRight,
  HardDrive,
  LayoutGrid,
  Loader2,
  RefreshCw,
  Target,
} from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  buildPhotoUrl,
  useBackupCheck,
  useBackupSync,
  useFolders,
  useMarkCompleted,
  usePhotos,
  useSources,
} from "@/lib/queries/nichoPovBof";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type { BackupCheckResponse } from "@/lib/types/nichoPovBof";

export default function NichoPovBofPage() {
  const [source, setSource] = useState("aleatorios_1");
  const [showAll, setShowAll] = useState(false);
  // Carpeta elegida a mano. Si es null se usa la "current" del backend
  // (la primera sin completar).
  const [picked, setPicked] = useState<string | null>(null);

  const sources = useSources();
  const folders = useFolders(source);
  const markCompleted = useMarkCompleted(source);

  const [backup, setBackup] = useState<BackupCheckResponse | null>(null);
  const backupCheck = useBackupCheck();
  const backupSync = useBackupSync();
  const openQueue = useDrawerStore((s) => s.openQueue);

  function checkBackup() {
    backupCheck.mutate(undefined, {
      onSuccess: (res) => {
        setBackup(res);
        toast.success(
          res.has_changes
            ? `${res.n_added} nuevos · ${res.n_modified} modificados · ${res.n_deleted} borrados en origen`
            : "Sin cambios desde la última copia",
        );
      },
      onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
    });
  }

  function syncBackup(forceFull: boolean) {
    backupSync.mutate(
      { force_full: forceFull },
      {
        onSuccess: () => {
          toast.success("Backup encolado");
          openQueue();
        },
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  const data = folders.data;
  const folder = picked ?? data?.current ?? null;
  const photos = usePhotos(source, folder);

  const idx = useMemo(
    () => (data && folder ? data.items.findIndex((f) => f.name === folder) : -1),
    [data, folder],
  );
  const currentItem = idx >= 0 ? data?.items[idx] : undefined;
  const done = data?.completed_count ?? 0;
  const total = data?.total ?? 0;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  function switchSource(slug: string) {
    setSource(slug);
    setPicked(null);
  }

  function step(delta: number) {
    if (!data || idx < 0) return;
    const next = data.items[idx + delta];
    if (next) setPicked(next.name);
  }

  function toggleCompleted(completed: boolean) {
    if (!folder) return;
    markCompleted.mutate(
      { source, folder, completed },
      {
        onSuccess: (res) => {
          if (completed) {
            toast.success(`"${folder}" completada`);
            // Avanzar a la siguiente sin hacer: es el flujo que pidió el user.
            setPicked(res.next_folder);
          } else {
            toast.success(`"${folder}" reabierta`);
          }
        },
        onError: (e) => {
          const msg = e instanceof ApiError ? e.message : String(e);
          toast.error(`No se pudo guardar: ${msg}`);
        },
      },
    );
  }

  return (
    <div className="container mx-auto space-y-5 p-4 sm:p-6 md:p-10">
      <header className="flex items-center gap-3">
        <Target className="h-6 w-6 shrink-0 text-emerald-500" />
        <div className="min-w-0">
          <h1 className="truncate text-xl font-bold sm:text-2xl">Nicho POV BOF</h1>
          <p className="truncate text-xs text-muted-foreground sm:text-sm">
            Productos del Drive compartido · solo lectura
          </p>
        </div>
      </header>

      {/* Fuente */}
      <section className="space-y-2">
        <div className="grid grid-cols-2 gap-2">
          {(sources.data?.items ?? []).map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => switchSource(s.slug)}
              className={`truncate rounded-lg border px-3 py-2 text-xs transition sm:text-sm ${
                source === s.slug
                  ? "border-emerald-500 bg-emerald-500/10 font-semibold text-emerald-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </section>

      {/* Progreso */}
      <section className="rounded-xl border border-border/60 bg-card p-3">
        <div className="mb-2 flex items-center justify-between text-xs sm:text-sm">
          <span className="font-medium">
            {done} / {total} completadas
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void folders.refetch()}
              className="rounded-md border border-border/60 p-1.5 text-muted-foreground transition hover:text-foreground"
              title="Recargar desde Drive"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${folders.isFetching ? "animate-spin" : ""}`} />
            </button>
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className={`flex items-center gap-1 rounded-md border px-2 py-1.5 text-[11px] transition sm:text-xs ${
                showAll
                  ? "border-emerald-500 text-emerald-500"
                  : "border-border/60 text-muted-foreground hover:text-foreground"
              }`}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              Ver todas
            </button>
          </div>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-emerald-500 transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      </section>

      {/* Backup del Drive de origen */}
      <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <HardDrive className="h-4 w-4 shrink-0 text-sky-500" />
          <p className="text-sm font-semibold">Copia de seguridad</p>
        </div>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          El Drive de origen es de un tercero y se borra sin aviso. Comprueba si
          han añadido o cambiado algo y guarda solo la diferencia.
        </p>

        {backup && (
          <div className="space-y-1 rounded-lg border border-border/60 bg-muted/40 p-2 text-[11px]">
            <p className="text-muted-foreground">
              Última copia:{" "}
              <span className="font-medium text-foreground">
                {backup.last_snapshot ?? "ninguna"}
              </span>
            </p>
            {backup.has_changes ? (
              <>
                <p>
                  <span className="font-semibold text-emerald-500">+{backup.n_added}</span> nuevos ·{" "}
                  <span className="font-semibold text-amber-500">~{backup.n_modified}</span> modificados ·{" "}
                  <span className="font-semibold text-red-500">-{backup.n_deleted}</span> borrados en origen
                </p>
                <p className="text-muted-foreground">
                  {Math.round(backup.change_ratio * 100)}% del archivo ({backup.n_total_source} ficheros).{" "}
                  {backup.would_be_full
                    ? "Se hará copia COMPLETA nueva."
                    : "Se copiará solo la diferencia."}
                </p>
              </>
            ) : (
              <p className="text-emerald-500">Sin cambios — no hay nada que copiar.</p>
            )}
          </div>
        )}

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={checkBackup}
            disabled={backupCheck.isPending}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
          >
            {backupCheck.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Comprobar cambios
          </button>
          <button
            type="button"
            onClick={() => syncBackup(false)}
            disabled={backupSync.isPending}
            className="flex items-center justify-center gap-1.5 rounded-lg bg-sky-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-sky-600 disabled:opacity-50"
          >
            {backupSync.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <HardDrive className="h-3.5 w-3.5" />
            )}
            Sincronizar
          </button>
        </div>
        <button
          type="button"
          onClick={() => syncBackup(true)}
          disabled={backupSync.isPending}
          className="w-full rounded-lg border border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:text-foreground disabled:opacity-50"
        >
          Forzar copia completa nueva
        </button>
        <p className="text-[10px] text-muted-foreground">
          También corre solo cada día a las 06:00.
        </p>
      </section>

      {folders.isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Leyendo el Drive compartido…
        </div>
      )}

      {folders.isError && (
        <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-500">
          {(folders.error as Error)?.message ?? "No se pudo leer el Drive."}
        </p>
      )}

      {/* Rejilla compacta de todas las carpetas (estilo calendario) */}
      {showAll && data && (
        <section className="rounded-xl border border-border/60 bg-card p-3">
          <div className="grid grid-cols-4 gap-1 sm:grid-cols-6 md:grid-cols-8">
            {data.items.map((f, i) => {
              const isSel = f.name === folder;
              return (
                <button
                  key={f.id || f.name}
                  type="button"
                  onClick={() => setPicked(f.name)}
                  title={f.name}
                  className={`flex aspect-square flex-col items-center justify-center rounded-lg border p-0.5 text-xs transition ${
                    f.completed
                      ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-500"
                      : "border-border/60 text-muted-foreground hover:border-foreground/30"
                  } ${isSel ? "ring-2 ring-emerald-500" : ""}`}
                >
                  <span className="font-semibold">{i + 1}</span>
                  {f.completed && <Check className="h-3 w-3" />}
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* Carpeta actual */}
      {data && !folder && (
        <p className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-4 text-center text-sm text-emerald-500">
          🎉 Todas las carpetas de esta fuente están completadas.
        </p>
      )}

      {data && folder && (
        <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => step(-1)}
              disabled={idx <= 0}
              className="rounded-md border border-border/60 p-1.5 disabled:opacity-30"
              aria-label="Anterior"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <div className="min-w-0 flex-1 text-center">
              <p className="truncate text-sm font-semibold sm:text-base">{folder}</p>
              <p className="text-[11px] text-muted-foreground">
                {idx + 1} de {total}
                {currentItem?.completed && " · ✅ completada"}
              </p>
            </div>
            <button
              type="button"
              onClick={() => step(1)}
              disabled={idx < 0 || idx >= total - 1}
              className="rounded-md border border-border/60 p-1.5 disabled:opacity-30"
              aria-label="Siguiente"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          {photos.isLoading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando fotos…
            </div>
          )}

          {photos.data && (
            <>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
                {photos.data.items.map((p) => (
                  <a
                    key={p.id}
                    href={buildPhotoUrl(source, folder, p.id)}
                    target="_blank"
                    rel="noreferrer"
                    className="group relative aspect-square overflow-hidden rounded-lg border border-border/60 bg-muted"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={buildPhotoUrl(source, folder, p.id)}
                      alt={p.name}
                      loading="lazy"
                      className="h-full w-full object-cover transition group-hover:scale-105"
                    />
                    <span className="absolute inset-x-0 bottom-0 truncate bg-black/60 px-1 py-0.5 text-[10px] text-white">
                      {p.name}
                    </span>
                  </a>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground">
                {photos.data.items.length} foto(s)
              </p>
            </>
          )}

          <button
            type="button"
            onClick={() => toggleCompleted(!currentItem?.completed)}
            disabled={markCompleted.isPending}
            className={`flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold transition disabled:opacity-50 ${
              currentItem?.completed
                ? "border border-border/60 text-muted-foreground hover:text-foreground"
                : "bg-emerald-500 text-white hover:bg-emerald-600"
            }`}
          >
            {markCompleted.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4" />
            )}
            {currentItem?.completed ? "Desmarcar completada" : "Completada · siguiente"}
          </button>
        </section>
      )}
    </div>
  );
}
