"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Caja } from "@/components/tiktok-shop-ai-pro/Paso";
import { BadgeReembolso } from "@/components/tiktok-shop-ai-pro/Reembolsable";
import { ApiError } from "@/lib/api";
import { admiteMarcas, useMarcarProducto, usePrioridades } from "@/lib/queries/nichoPovBof";
import type { MarcasInfo } from "@/lib/types/nichoPovBof";

/** Marcas de un producto de los catálogos del operador (`services/marcas.py`):
 *  🎥 físico, 📣 necesita contenido (N vídeos, se descuentan al marcar subido
 *  en Mis tandas), 🎄 funciona en Q4 y 📁 carpeta de clips reales. Varias a la
 *  vez; la reembolsable va aparte (Reembolsable.tsx).
 *
 *  Colores: ámbar = le falta contenido, esmeralda = contenido hecho; cian
 *  para lo físico/real (no lo usa ningún color con significado de UI_NICHOS).
 */

function err(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

const VACIAS: MarcasInfo = {
  fisico: false,
  fisico_por_catalogo: false,
  q4: false,
  clips_reales: "",
  contenido: null,
};

const FORMATOS_UI = [
  { clave: "ia", icono: "🤖", nombre: "IA", defecto: 5 },
  { clave: "viral", icono: "🔁", nombre: "Viral", defecto: 1 },
  { clave: "fisico", icono: "🎥", nombre: "Físico", defecto: 0 },
] as const;

/** «🤖 IA 0/5 · 🔁 Viral 0/1»: vídeos subidos por formato; esmeralda al llegar. */
function LineaFormatos({ info }: { info: MarcasInfo }) {
  const visibles = FORMATOS_UI.map((f) => ({ f, c: info.formatos?.[f.clave] })).filter(
    (x): x is { f: (typeof FORMATOS_UI)[number]; c: NonNullable<typeof x.c> } =>
      !!x.c && (x.c.objetivo > 0 || x.c.subidos > 0),
  );
  if (!visibles.length) return null;
  return (
    <p className="flex w-full flex-wrap gap-x-2 text-[10px] sm:text-xs">
      {visibles.map(({ f, c }) => (
        <span
          key={f.clave}
          title={`Vídeos ${f.nombre} subidos / objetivo`}
          className={c.hecho ? "font-semibold text-emerald-500" : "text-muted-foreground"}
        >
          {f.icono} {f.nombre} {c.subidos}/{c.objetivo}
        </span>
      ))}
    </p>
  );
}

/** Diálogo de contenido + clips reales (lo que lleva un número o un texto). */
function DialogoMarcas({
  abierto,
  onCerrar,
  source,
  folder,
  producto,
  titulo,
  info,
}: {
  abierto: boolean;
  onCerrar: () => void;
  source: string;
  folder: string;
  producto: string;
  titulo: string;
  info: MarcasInfo;
}) {
  const marcar = useMarcarProducto();
  const [pide, setPide] = useState(false);
  const [videos, setVideos] = useState("1");
  const [clips, setClips] = useState("");
  const [objs, setObjs] = useState<Record<string, string>>({ ia: "5", viral: "1", fisico: "0" });

  useEffect(() => {
    if (!abierto) return;
    setPide(!!info.contenido);
    setVideos(String(info.contenido?.videos ?? 1));
    setClips(info.clips_reales);
    setObjs(
      Object.fromEntries(
        FORMATOS_UI.map((f) => [f.clave, String(info.formatos?.[f.clave]?.objetivo ?? f.defecto)]),
      ),
    );
  }, [abierto, info]);

  const nVideos = Number.parseInt(videos, 10);
  const objsOk = FORMATOS_UI.every((f) => {
    const n = Number.parseInt(objs[f.clave] ?? "", 10);
    return n >= 0 && n <= 20;
  });
  const valido = (!pide || (nVideos >= 1 && nVideos <= 20)) && objsOk;
  const guardar = () => {
    marcar.mutate(
      {
        source,
        folder,
        producto,
        clips_reales: clips.trim(),
        objetivo_ia: Number.parseInt(objs.ia ?? "", 10),
        objetivo_viral: Number.parseInt(objs.viral ?? "", 10),
        objetivo_fisico: Number.parseInt(objs.fisico ?? "", 10),
        ...(pide ? { contenido_videos: nVideos } : info.contenido ? { contenido: false } : {}),
      },
      {
        onSuccess: () => {
          toast.success("Marcas guardadas");
          onCerrar();
        },
        onError: (e) => toast.error(err(e)),
      },
    );
  };
  const campo =
    "w-full rounded-lg border border-border/60 bg-background px-2 py-1.5 text-xs outline-none focus:border-cyan-500/60 sm:text-sm";

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="w-[calc(100vw-2rem)] max-w-md max-h-[90vh] overflow-y-auto rounded-xl p-4 sm:p-6">
        <DialogHeader>
          <DialogTitle className="text-base">🏷️ Marcas del producto</DialogTitle>
          <DialogDescription className="break-words text-xs sm:text-sm">
            {producto} · {titulo || "Producto"}
          </DialogDescription>
        </DialogHeader>
        <label className="flex items-center gap-2 text-xs sm:text-sm">
          <input type="checkbox" checked={pide} onChange={(e) => setPide(e.target.checked)} />
          📣 Necesita contenido (la tienda pide vídeos)
        </label>
        {pide && (
          <label className="block space-y-1">
            <span className="text-[11px] font-medium text-muted-foreground">
              Vídeos que pide{info.contenido ? ` (lleva ${info.contenido.subidos} subidos)` : ""}
            </span>
            <input
              type="number"
              inputMode="numeric"
              min={1}
              max={20}
              value={videos}
              onChange={(e) => setVideos(e.target.value)}
              className={campo}
            />
            <span className="block text-[10px] text-muted-foreground">
              Cada vídeo de este producto marcado «Subido» en Mis tandas descuenta uno.
            </span>
          </label>
        )}
        <label className="block space-y-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            📁 Carpeta de clips reales (ruta del Drive o enlace, opcional)
          </span>
          <input
            type="text"
            value={clips}
            placeholder="TIKTOK_SHOP_AI_PRO/Clips_reales/bici"
            onChange={(e) => setClips(e.target.value)}
            className={campo}
          />
        </label>
        <div className="space-y-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            🎯 Vídeos a subir por formato (0 = no se pide)
          </span>
          <div className="grid grid-cols-3 gap-2">
            {FORMATOS_UI.map((f) => (
              <label key={f.clave} className="block space-y-0.5">
                <span className="text-[10px] text-muted-foreground">
                  {f.icono} {f.nombre} ({info.formatos?.[f.clave]?.subidos ?? 0} subidos)
                </span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={20}
                  value={objs[f.clave] ?? ""}
                  onChange={(e) => setObjs((o) => ({ ...o, [f.clave]: e.target.value }))}
                  className={campo}
                />
              </label>
            ))}
          </div>
        </div>
        <DialogFooter className="flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={onCerrar}
            className="rounded-lg border border-border/60 px-3 py-2 text-xs font-medium text-muted-foreground transition hover:text-foreground sm:text-sm"
          >
            Cancelar
          </button>
          <button
            type="button"
            disabled={marcar.isPending || !valido}
            onClick={guardar}
            className="rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-700 disabled:opacity-50 sm:text-sm"
          >
            {marcar.isPending ? "Guardando…" : "Guardar"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Fila «🏷️» de la tarjeta: chips que se encienden/apagan con un toque
 *  (físico, Q4) y el diálogo para contenido y clips reales. */
export function MarcasTarjeta({
  source,
  folder,
  producto,
  titulo,
  info,
}: {
  source: string;
  folder: string;
  producto: string;
  titulo: string;
  info: MarcasInfo | null | undefined;
}) {
  const [abierto, setAbierto] = useState(false);
  const marcar = useMarcarProducto();
  if (!admiteMarcas(source) || !folder) return null;
  const m = info ?? VACIAS;
  const c = m.contenido;

  const alternar = (campo: "fisico" | "q4", valor: boolean) =>
    marcar.mutate(
      { source, folder, producto, [campo]: valor },
      { onError: (e) => toast.error(err(e)) },
    );

  const chip = "rounded-full border px-2 py-0.5 text-[10px] font-semibold transition disabled:opacity-50";
  const apagado = "border-dashed border-border/60 text-muted-foreground hover:text-foreground";
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      {m.fisico_por_catalogo ? (
        <span className={`${chip} border-cyan-500/50 bg-cyan-500/10 text-cyan-500`} title="Está en Productos físicos">
          🎥 Físico
        </span>
      ) : (
        <button
          type="button"
          disabled={marcar.isPending}
          onClick={() => alternar("fisico", !m.fisico)}
          title="Lo tienes en casa: se pueden grabar vídeos reales"
          className={`${chip} ${m.fisico ? "border-cyan-500/50 bg-cyan-500/10 text-cyan-500" : apagado}`}
        >
          🎥 {m.fisico ? "Físico" : "¿Físico?"}
        </button>
      )}
      <button
        type="button"
        onClick={() => setAbierto(true)}
        title={c ? `La tienda pide ${c.videos} vídeo(s); llevas ${c.subidos} subidos` : "¿La tienda pide vídeos?"}
        className={`${chip} ${
          !c
            ? apagado
            : c.hecho
              ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-500"
              : "border-amber-500/60 bg-amber-500/15 text-amber-500"
        }`}
      >
        📣 {!c ? "¿Contenido?" : c.hecho ? `Contenido hecho ${c.subidos}/${c.videos}` : `Contenido ${c.subidos}/${c.videos}`}
      </button>
      <button
        type="button"
        disabled={marcar.isPending}
        onClick={() => alternar("q4", !m.q4)}
        title="Funciona ahora en Q4"
        className={`${chip} ${m.q4 ? "border-border bg-muted text-foreground" : apagado}`}
      >
        🎄 {m.q4 ? "Q4" : "¿Q4?"}
      </button>
      <LineaFormatos info={m} />
      {m.clips_reales && (
        <button
          type="button"
          onClick={() => setAbierto(true)}
          title={m.clips_reales}
          className={`${chip} max-w-[10rem] truncate border-cyan-500/50 text-cyan-500`}
        >
          📁 Clips reales
        </button>
      )}
      <DialogoMarcas
        abierto={abierto}
        onCerrar={() => setAbierto(false)}
        source={source}
        folder={folder}
        producto={producto}
        titulo={titulo}
        info={m}
      />
    </div>
  );
}

type Grupo = { icono: string; nombre: string; clase: string };
const RESTO: Grupo = { icono: "🎄", nombre: "Resto", clase: "text-muted-foreground" };
const GRUPOS: Record<string, Grupo> = {
  contenido: { icono: "📣", nombre: "Necesita contenido", clase: "text-amber-500" },
  reembolso: { icono: "💸", nombre: "Reembolsables", clase: "text-teal-500" },
  resto: RESTO,
};

/** Caja «🎯 Prioridades»: qué producto toca en los catálogos del operador.
 *  1) necesita contenido (el que menos le falta), 2) reembolsables (el que
 *  más dinero devuelve), 3) opcional, el resto con Q4 primero. */
export function CajaPrioridades({ source }: { source?: string }) {
  const [soloFisicos, setSoloFisicos] = useState(false);
  const [resto, setResto] = useState(false);
  const q = usePrioridades({ source, soloFisicos, incluirResto: resto, limite: resto ? 60 : 0 });
  const d = q.data;
  const chip = "rounded-full border px-2 py-0.5 text-[10px] font-semibold transition";
  return (
    <Caja
      icono="🎯"
      titulo="Prioridades"
      hint="Qué hacer primero: lo que necesita contenido (el que menos vídeos le faltan), luego los reembolsables (el que más dinero devuelve)."
      extra={d ? `${d.contenido} contenido · ${d.reembolso} reembolso` : undefined}
    >
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          onClick={() => setSoloFisicos((v) => !v)}
          className={`${chip} ${soloFisicos ? "border-cyan-500/50 bg-cyan-500/10 text-cyan-500" : "border-border/60 text-muted-foreground"}`}
        >
          🎥 Solo físicos
        </button>
        <button
          type="button"
          onClick={() => setResto((v) => !v)}
          className={`${chip} ${resto ? "border-border bg-muted text-foreground" : "border-border/60 text-muted-foreground"}`}
        >
          🎄 Ver también el resto
        </button>
      </div>
      {q.isLoading && <p className="text-[10px] text-muted-foreground">Cargando…</p>}
      {d && !d.items.length && (
        <p className="text-[10px] text-muted-foreground">
          Nada con prioridad. Marca «📣 ¿Contenido?» o «💸 ¿Reembolsable?» en la tarjeta del producto o al subirlo.
        </p>
      )}
      <ul className="space-y-1">
        {d?.items.map((i) => {
          const g = GRUPOS[i.grupo || "resto"] ?? RESTO;
          return (
            <li
              key={`${i.source}|${i.folder}|${i.producto}`}
              className="flex flex-col gap-0.5 rounded-lg border border-border/60 px-2 py-1.5 sm:flex-row sm:items-center sm:gap-2"
            >
              <span className="flex min-w-0 items-baseline gap-1.5 text-[11px] sm:flex-1">
                <span className={`shrink-0 ${g.clase}`} title={g.nombre}>{g.icono}</span>
                <span className="shrink-0 rounded bg-muted px-1 font-mono text-[9px] text-muted-foreground">
                  {i.folder.replace(/^(Mis Productos|Productos Fisicos|Tareas Productos)\s*/, "C")}·{i.producto}
                </span>
                {i.catalogo && (
                  <span className="hidden shrink-0 rounded border border-border/60 px-1 text-[9px] text-muted-foreground sm:inline">
                    {i.catalogo}
                  </span>
                )}
                {i.marcas.fisico && <span className="shrink-0 text-[10px]" title="Físico">🎥</span>}
                <span className="truncate">{i.titulo || "sin título"}</span>
              </span>
              {i.grupo === "reembolso" && i.reembolso ? (
                <BadgeReembolso info={i.reembolso} className="shrink-0" />
              ) : (
                <span className="shrink-0 truncate text-[10px] text-muted-foreground">{i.motivo}</span>
              )}
            </li>
          );
        })}
      </ul>
    </Caja>
  );
}
