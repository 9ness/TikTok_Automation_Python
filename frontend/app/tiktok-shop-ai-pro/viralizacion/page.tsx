"use client";

import { useEffect, useState } from "react";
import { Loader2, Palette, Rocket } from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  useCarpetas,
  useEstilos,
  useGenerateViralizacion,
  usePonentes,
  useRoundPlan,
} from "@/lib/queries/viralizacion";
import { useDrawerStore } from "@/lib/stores/drawerStore";

export default function ViralizacionPage() {
  const openQueue = useDrawerStore((s) => s.openQueue);
  const ponentesQuery = usePonentes();
  const generate = useGenerateViralizacion();

  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [cantidad, setCantidad] = useState<Record<string, number>>({});
  const [nombreCuenta, setNombreCuenta] = useState("");
  const [musicRounds, setMusicRounds] = useState(1);
  const [success, setSuccess] = useState<{ total: number; position: number } | null>(null);

  const ponentes = ponentesQuery.data?.items ?? [];
  const selectedSlugs = Object.keys(selected).filter((slug) => selected[slug]);

  // Estilo por ronda. El plan se calcula sobre el primer ponente elegido: el
  // reparto en rondas depende de cuántos audios tiene, y las rondas son el
  // "ciclo" que el operador quiere diferenciar.
  // "__nueva__" = escribir un nombre a mano; si no, se reutiliza una carpeta
  // que ya existe en Drive.
  const [carpetaExistente, setCarpetaExistente] = useState("__nueva__");
  const carpetas = useCarpetas();
  const today = new Date().toISOString().slice(0, 10);

  const [roundStyles, setRoundStyles] = useState<string[]>([]);
  const estilos = useEstilos();
  const planPonente = selectedSlugs[0] ?? null;
  const planCantidad = planPonente ? (cantidad[planPonente] ?? 5) : 0;
  const plan = useRoundPlan(planPonente, planCantidad);

  // Al cambiar el reparto, arrancar desde los estilos por defecto (la
  // rotación) para que lo que se envía siempre case con las rondas reales.
  useEffect(() => {
    const rounds = plan.data?.rounds;
    if (rounds) setRoundStyles(rounds.map((r) => r.default_style));
  }, [plan.data]);

  const canSubmit =
    selectedSlugs.length > 0 && nombreCuenta.trim().length > 0 && !generate.isPending;

  function toggle(slug: string, checked: boolean) {
    setSelected((prev) => ({ ...prev, [slug]: checked }));
    setCantidad((prev) => (prev[slug] != null ? prev : { ...prev, [slug]: 5 }));
  }

  async function submit() {
    if (!canSubmit) return;
    setSuccess(null);
    const body = {
      ponentes: selectedSlugs,
      cantidad: Object.fromEntries(
        selectedSlugs.map((slug) => [slug, cantidad[slug] ?? 5]),
      ),
      nombre_cuenta: nombreCuenta.trim(),
      music_rounds: musicRounds,
      round_styles: roundStyles,
    };
    try {
      const res = await generate.mutateAsync(body);
      toast.success(`Job encolado — ${res.total_videos} vídeos · posición ${res.position_in_queue} en la cola`);
      setSuccess({ total: res.total_videos, position: res.position_in_queue });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error inesperado");
    }
  }

  return (
    <div className="container mx-auto space-y-6 p-4 sm:p-6 md:p-10">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-xl font-bold sm:text-2xl">
          <Rocket className="h-5 w-5 text-amber-500 sm:h-6 sm:w-6" />
          Viralización 1K
        </h1>
        <p className="text-xs text-muted-foreground sm:text-sm">
          Genera en lote vídeos POV/reacción (voz de ponente + B-roll paisaje) para
          hacer crecer una cuenta hasta 1000 seguidores.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold sm:text-base">Ponentes</h2>
        {ponentesQuery.isLoading && (
          <p className="text-xs text-muted-foreground">Cargando ponentes…</p>
        )}
        {ponentesQuery.isError && (
          <p className="text-xs text-destructive">No se pudieron cargar los ponentes.</p>
        )}
        {!ponentesQuery.isLoading && ponentes.length === 0 && !ponentesQuery.isError && (
          <p className="text-xs text-muted-foreground">No hay ponentes disponibles.</p>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {ponentes.map((p) => {
            const disabled = p.n_audios <= 0;
            const isSelected = !disabled && !!selected[p.slug];
            return (
              <div
                key={p.slug}
                className="space-y-2 rounded-lg border border-border p-3 text-xs sm:text-sm"
              >
                <label className="flex cursor-pointer items-start gap-2">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 shrink-0 accent-amber-500"
                    checked={isSelected}
                    disabled={disabled}
                    onChange={(e) => toggle(p.slug, e.target.checked)}
                  />
                  <span>
                    <span className="font-medium">{p.label}</span>
                    {" — "}
                    {p.n_audios} audio{p.n_audios === 1 ? "" : "s"} disponible
                    {p.n_audios === 1 ? "" : "s"}
                    <span className="block text-[10px] text-muted-foreground">
                      gancho: {p.hooks_available}/{p.hooks_total} libres · paisaje:{" "}
                      {p.paisajes_available}/{p.paisajes_total} libres
                    </span>
                    {disabled && (
                      <span className="block text-[10px] text-destructive">
                        Sin audios disponibles — no se puede seleccionar.
                      </span>
                    )}
                  </span>
                </label>
                {isSelected && (
                  <div className="flex items-center gap-2 pl-6">
                    <span className="text-[11px] text-muted-foreground">¿Cuántos vídeos?</span>
                    <input
                      type="number"
                      min={1}
                      value={cantidad[p.slug] ?? 5}
                      onChange={(e) =>
                        setCantidad((prev) => ({
                          ...prev,
                          [p.slug]: Math.max(1, Number(e.target.value) || 1),
                        }))
                      }
                      className="w-16 rounded-md border border-border bg-background px-2 py-0.5 text-xs"
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="col-span-2 sm:col-span-1">
          <span className="mb-1 block text-xs font-medium sm:text-sm">
            Carpeta de destino *
          </span>
          {/* Desplegable con las carpetas que ya existen en Drive, para no
              tener que recordar el nombre exacto y poder acumular tandas. */}
          <select
            value={carpetaExistente}
            onChange={(e) => {
              const v = e.target.value;
              setCarpetaExistente(v);
              if (v !== "__nueva__") setNombreCuenta(v);
              else setNombreCuenta("");
            }}
            className="mb-1.5 w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs sm:text-sm"
          >
            <option value="__nueva__">➕ Carpeta nueva…</option>
            {(carpetas.data?.items ?? []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          {carpetaExistente === "__nueva__" && (
            <input
              type="text"
              value={nombreCuenta}
              onChange={(e) => setNombreCuenta(e.target.value)}
              placeholder="nombre de la carpeta nueva"
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs sm:text-sm"
            />
          )}
          <p className="mt-1 text-[10px] text-muted-foreground">
            Se guardará en <code>VIRALIZACION/{nombreCuenta || "…"}/</code>, con
            una subcarpeta por ponente (p. ej. <code>32_pablo_{today}</code>).
          </p>
        </div>
        <div>
          <span className="mb-1 block text-xs font-medium sm:text-sm">Rondas con música</span>
          <input
            type="number"
            min={0}
            value={musicRounds}
            onChange={(e) => setMusicRounds(Math.max(0, Number(e.target.value) || 0))}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs sm:text-sm"
          />
        </div>
      </section>

      {/* Estilo por ronda ("ciclo"): así cada pasada se ve distinta */}
      {plan.data && plan.data.rounds.length > 0 && (
        <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
          <div className="flex items-center gap-2">
            <Palette className="h-4 w-4 shrink-0 text-amber-500" />
            <p className="text-sm font-semibold">Estilo de cada ronda</p>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Los vídeos se reparten entre los audios en rondas. Elige un estilo
            por ronda para que cada ciclo se vea distinto.
          </p>
          <div className="space-y-2">
            {plan.data.rounds.map((r, i) => (
              <div key={r.ronda} className="flex items-center gap-2">
                <span className="w-28 shrink-0 text-[11px] sm:text-xs">
                  Ronda {r.ronda}
                  <span className="text-muted-foreground"> · {r.n_videos} vídeo(s)</span>
                </span>
                <select
                  value={roundStyles[i] ?? r.default_style}
                  onChange={(e) =>
                    setRoundStyles((prev) => {
                      const next = [...prev];
                      while (next.length < plan.data!.rounds.length) next.push("");
                      next[i] = e.target.value;
                      return next;
                    })
                  }
                  className="flex-1 truncate rounded-md border border-border bg-background px-2 py-1.5 text-xs sm:text-sm"
                >
                  {(estilos.data?.items ?? []).map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          {planPonente && (
            <p className="text-[10px] text-muted-foreground">
              Reparto calculado para <b>{planPonente}</b> con {planCantidad} vídeos.
            </p>
          )}
        </section>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!canSubmit}
          onClick={submit}
          className="inline-flex items-center gap-1.5 rounded-md bg-amber-500 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-50"
        >
          {generate.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
          {generate.isPending ? "Encolando…" : "Generar"}
        </button>
        {success && (
          <button
            type="button"
            onClick={openQueue}
            className="text-xs font-medium text-amber-600 hover:underline sm:text-sm"
          >
            Ver cola →
          </button>
        )}
      </div>
    </div>
  );
}
