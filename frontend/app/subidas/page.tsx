"use client";

import { ChevronLeft, ChevronRight, Loader2, Upload } from "lucide-react";
import { useMemo, useState } from "react";

import { GuiaIA } from "@/components/tiktok-shop-ai-pro/GuiaIA";
import { cn } from "@/lib/utils";
import { useMe } from "@/lib/queries/auth";
import { type DiaSubidas, useSubidas } from "@/lib/queries/subidas";

/** Objetivo diario de la cuenta árabe (docs/CUENTA_ARABE.md): 45 carruseles
 *  y 10 vídeos. Los primeros días se sube menos (15 + 5-10). */
const OBJETIVO_CARRUSELES = 45;
const OBJETIVO_VIDEOS = 10;

/** Quién tiene contador. El backend lo corta también (`src/api/routers/subidas.py`). */
const USUARIOS = ["nes_bugallo", "ness"];
const NOMBRES: Record<string, string> = { nes_bugallo: "Ness/Bugallo", ness: "ness" };

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
const DIAS_SEMANA = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

/** Hoy en Madrid como `YYYY-MM-DD` (lo mismo que usa el backend). */
function hoyMadrid(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Madrid" }).format(new Date());
}

function moverMes(mes: string, delta: number): string {
  const a = Number(mes.slice(0, 4));
  const m = Number(mes.slice(5, 7)) - 1 + delta;
  const d = new Date(Date.UTC(a, m, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

const nombreMes = (mes: string) => `${MESES[Number(mes.slice(5, 7)) - 1]} ${mes.slice(0, 4)}`;
const num = (n: number) => n.toLocaleString("es-ES", { maximumFractionDigits: 1 });

/** Los días del mes ya empezados, del más reciente al más antiguo, con lo
 *  apuntado (o vacío): así se ven también los días sin subida. */
function diasDelMes(mes: string, hoy: string, apuntados: DiaSubidas[]): DiaSubidas[] {
  const por = new Map(apuntados.map((d) => [d.fecha, d]));
  const a = Number(mes.slice(0, 4));
  const m = Number(mes.slice(5, 7));
  const total = new Date(Date.UTC(a, m, 0)).getUTCDate();
  const out: DiaSubidas[] = [];
  for (let d = 1; d <= total; d++) {
    const fecha = `${mes}-${String(d).padStart(2, "0")}`;
    if (fecha > hoy && !por.has(fecha)) continue;
    out.push(por.get(fecha) ?? { fecha, videos: 0, carruseles: 0, nota: "", actualizado: "" });
  }
  return out.reverse();
}

function Dato({
  label, valor, sub, ok,
}: { label: string; valor: string; sub?: string; ok?: boolean }) {
  return (
    <div className="rounded-lg border border-border/60 bg-card p-3">
      <p className="text-[11px] text-muted-foreground sm:text-xs">{label}</p>
      <p className="text-lg font-bold sm:text-xl">{valor}</p>
      {sub ? (
        <p
          className={cn(
            "text-[11px]",
            ok === undefined ? "text-muted-foreground" : ok ? "text-emerald-500" : "text-amber-500",
          )}
        >
          {sub}
        </p>
      ) : null}
    </div>
  );
}

export default function SubidasPage() {
  const me = useMe();
  const yo = me.data?.username ?? "";
  const permitido = USUARIOS.includes(yo);
  const esAdmin = me.data?.rol === "admin";
  const hoy = hoyMadrid();
  const [mes, setMes] = useState(hoy.slice(0, 7));
  // El admin mira por defecto la cuenta árabe, que es para lo que existe esto.
  const [deQuien, setDeQuien] = useState<string>("");
  const usuario = esAdmin ? deQuien || "nes_bugallo" : "";
  const q = useSubidas(mes, usuario, permitido);

  const t = q.data?.totales;
  const dias = useMemo(() => diasDelMes(mes, hoy, q.data?.dias ?? []), [mes, hoy, q.data]);

  if (me.isLoading) return <Loader2 className="m-6 h-5 w-5 animate-spin" />;
  if (!permitido) {
    return <p className="p-6 text-sm text-muted-foreground">Tu usuario no tiene contador de subidas.</p>;
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24 sm:space-y-4">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Upload className="h-5 w-5 shrink-0 text-violet-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Subidas</h1>
            <p className="text-[11px] text-muted-foreground">
              Vídeos y carruseles publicados cada día, con el total del mes
            </p>
          </div>
          <GuiaIA guia="subidas" />
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground sm:text-xs">
          Lo apuntan los agentes al terminar cada tanda de subida. Objetivo diario:{" "}
          <span className="font-semibold text-foreground">
            {OBJETIVO_CARRUSELES} carruseles + {OBJETIVO_VIDEOS} vídeos
          </span>{" "}
          (los primeros días, 15 + 5-10).
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1 rounded-md border border-border/60 bg-card">
          <button
            type="button"
            onClick={() => setMes(moverMes(mes, -1))}
            className="p-2 text-muted-foreground hover:text-foreground"
            aria-label="Mes anterior"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-[8.5rem] text-center text-sm font-semibold capitalize">
            {nombreMes(mes)}
          </span>
          <button
            type="button"
            onClick={() => setMes(moverMes(mes, 1))}
            disabled={mes >= hoy.slice(0, 7)}
            className="p-2 text-muted-foreground hover:text-foreground disabled:opacity-30"
            aria-label="Mes siguiente"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        {esAdmin ? (
          <div className="ml-auto flex flex-wrap gap-1">
            {USUARIOS.map((u) => (
              <button
                key={u}
                type="button"
                onClick={() => setDeQuien(u)}
                className={cn(
                  "rounded border px-2 py-1 text-xs transition",
                  usuario === u
                    ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
                    : "border-border/60 text-muted-foreground hover:border-foreground/40",
                )}
              >
                {NOMBRES[u] ?? u}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {q.isLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : null}
      {q.isError ? <p className="text-sm text-red-500">No se pudieron cargar las subidas.</p> : null}

      {t ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Dato
            label="Carruseles"
            valor={num(t.carruseles)}
            sub={`${num(t.media_dia.carruseles)}/día · objetivo ${OBJETIVO_CARRUSELES}`}
            ok={t.dias_transcurridos ? t.media_dia.carruseles >= OBJETIVO_CARRUSELES : undefined}
          />
          <Dato
            label="Vídeos"
            valor={num(t.videos)}
            sub={`${num(t.media_dia.videos)}/día · objetivo ${OBJETIVO_VIDEOS}`}
            ok={t.dias_transcurridos ? t.media_dia.videos >= OBJETIVO_VIDEOS : undefined}
          />
          <Dato
            label="Total del mes"
            valor={num(t.total)}
            sub={`${num(t.media_dia.total)}/día · objetivo ${OBJETIVO_CARRUSELES + OBJETIVO_VIDEOS}`}
            ok={t.dias_transcurridos ? t.media_dia.total >= OBJETIVO_CARRUSELES + OBJETIVO_VIDEOS : undefined}
          />
          <Dato
            label="Días con subida"
            valor={`${t.dias_con_subida}/${t.dias_transcurridos}`}
            sub="días del mes ya empezados"
          />
        </div>
      ) : null}

      {q.data ? (
        <section className="space-y-2 rounded-lg border border-border/60 bg-card/50 p-3 sm:p-4">
          <h2 className="text-sm font-semibold sm:text-base">Día a día</h2>
          {dias.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs sm:text-sm">
                <thead>
                  <tr className="border-b border-border/60 text-left text-muted-foreground">
                    <th className="py-1.5 pr-2 font-medium">Día</th>
                    <th className="px-2 py-1.5 text-right font-medium">Carruseles</th>
                    <th className="px-2 py-1.5 text-right font-medium">Vídeos</th>
                    <th className="py-1.5 pl-2 font-medium">Nota</th>
                  </tr>
                </thead>
                <tbody>
                  {dias.map((d) => {
                    const vacio = !d.videos && !d.carruseles;
                    const f = new Date(`${d.fecha}T12:00:00Z`);
                    return (
                      <tr
                        key={d.fecha}
                        className={cn("border-b border-border/30 align-top", vacio && "text-muted-foreground")}
                      >
                        <td className="whitespace-nowrap py-1.5 pr-2">
                          {DIAS_SEMANA[f.getUTCDay()]} {Number(d.fecha.slice(8, 10))}
                          {d.fecha === hoy ? <span className="ml-1 text-[10px] text-violet-500">hoy</span> : null}
                        </td>
                        <td
                          className={cn(
                            "px-2 py-1.5 text-right font-semibold tabular-nums",
                            !vacio && (d.carruseles >= OBJETIVO_CARRUSELES ? "text-emerald-500" : "text-amber-500"),
                          )}
                        >
                          {vacio ? "—" : d.carruseles}
                        </td>
                        <td
                          className={cn(
                            "px-2 py-1.5 text-right font-semibold tabular-nums",
                            !vacio && (d.videos >= OBJETIVO_VIDEOS ? "text-emerald-500" : "text-amber-500"),
                          )}
                        >
                          {vacio ? "—" : d.videos}
                        </td>
                        <td className="break-words py-1.5 pl-2 text-[11px] text-muted-foreground sm:text-xs">
                          {d.nota}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Este mes aún no ha empezado.</p>
          )}
        </section>
      ) : null}
    </div>
  );
}
