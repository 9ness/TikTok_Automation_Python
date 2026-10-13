"use client";

import { useState } from "react";
import Link from "next/link";
import { Clapperboard, Download, ExternalLink, Loader2, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { GuiaIA } from "@/components/tiktok-shop-ai-pro/GuiaIA";
import { Caja, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import { MODOS_RV } from "@/lib/tiktok-shop-ai-pro/coloresModo";
import { useMe } from "@/lib/queries/auth";
import {
  type ModoReplicaVideo,
  type ReplicaVideo,
  urlVideoReplica,
  useBorrarReplicaVideo,
  useRegistrarReplicaVideo,
  useReplicasVideo,
} from "@/lib/queries/replicarVirales";

const MODOS: { clave: ModoReplicaVideo; label: string; hint: string }[] = [
  { clave: "con_ia", label: "🤖 Con IA (Omni)", hint: "Clips de 10 s en Omni (GenAI Pro) con la foto del producto como ingrediente." },
  { clave: "sin_ia", label: "🎥 Sin IA (real)", hint: "Vídeo grabado o montaje sin IA del viral con nuestro producto." },
];

const INPUT = "w-full min-w-0 rounded-lg border border-border/60 bg-background px-3 py-2 text-xs";

/** «Replicar virales»: el MP4 YA MONTADO de un viral replicado (lo hace sobre
 *  todo el agente, por MCP `registrar_replica_video`). Aquí se da de alta a
 *  mano y se ve la lista; publicar se hace desde Mis tandas
 *  (`src/replicar_viral/video.py`). */
export default function ReplicarViralesPage() {
  const [modo, setModo] = useState<ModoReplicaVideo>("con_ia");
  const [filtro, setFiltro] = useState<"" | ModoReplicaVideo>("");
  const lista = useReplicasVideo(filtro);
  const todos = useReplicasVideo("");
  const me = useMe();
  const esAdmin = me.data?.rol === "admin";
  const otros = (me.data?.usuarios ?? []).filter((u) => u.username !== me.data?.username);

  const cuenta = (m: ModoReplicaVideo) => (todos.data?.items ?? []).filter((r) => r.modo === m).length;
  const subidas = (m: ModoReplicaVideo) =>
    (todos.data?.items ?? []).filter((r) => r.modo === m && r.uploaded).length;
  const total = todos.data?.items.length ?? 0;
  const hechas = (todos.data?.items ?? []).filter((r) => r.uploaded).length;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24 sm:space-y-4">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Clapperboard className="h-5 w-5 shrink-0 text-teal-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Replicar virales</h1>
            <p className="text-[11px] text-muted-foreground">
              Vídeos virales replicados con nuestro producto, ya montados
            </p>
          </div>
          <GuiaIA guia="replicar-virales" />
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
          El vídeo se monta fuera (con IA en Omni o sin IA, grabado) y aquí se registra con el nombre y
          el enlace del producto. Sale solo en <b>Mis tandas</b>, con su semáforo, para publicarlo.
        </p>
      </header>

      <Caja icono="📁" titulo="Dónde trabajas" hint="Elige el modo de la réplica." extra={`${hechas}/${total}`}>
        <Sub>Modo</Sub>
        <div className="grid grid-cols-2 gap-1.5">
          {MODOS.map((m) => (
            <button
              key={m.clave}
              type="button"
              onClick={() => setModo(m.clave)}
              className={`flex items-center justify-between gap-1 truncate rounded-lg border px-2 py-1.5 text-[11px] ${
                modo === m.clave
                  ? "border-sky-500 bg-sky-500/10 text-sky-400"
                  : "border-border/60 text-muted-foreground hover:text-foreground"
              }`}
            >
              <span className="truncate">{m.label}</span>
              <span className="shrink-0 rounded-full bg-muted px-1.5 text-[9px]">
                {subidas(m.clave)}/{cuenta(m.clave)}
              </span>
            </button>
          ))}
        </div>
        <p className="text-[10px] text-muted-foreground">{MODOS.find((m) => m.clave === modo)?.hint}</p>
      </Caja>

      <FormularioAlta modo={modo} esAdmin={esAdmin} otros={otros} />

      <Paso
        n={2}
        color="azul"
        titulo="Tus réplicas"
        hint="Lo último primero. Se publican desde Mis tandas (subido, sin stock, rehacer, semáforo)."
        extra={lista.data ? `${lista.data.items.length}` : undefined}
      >
        <div className="flex flex-wrap gap-1">
          {([["", "Todas"], ...MODOS.map((m) => [m.clave, m.label])] as [string, string][]).map(([k, l]) => (
            <button
              key={k || "todas"}
              type="button"
              onClick={() => setFiltro(k as "" | ModoReplicaVideo)}
              className={`rounded border px-2 py-1 text-[10px] ${
                filtro === k
                  ? "border-sky-500 bg-sky-500/10 text-sky-400"
                  : "border-border/60 text-muted-foreground hover:text-foreground"
              }`}
            >
              {l}
            </button>
          ))}
          <Link
            href="/tiktok-shop-ai-pro/mis-tandas"
            className="ml-auto flex items-center gap-1 rounded border border-border/60 px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground"
          >
            <ExternalLink className="h-3 w-3" /> Mis tandas
          </Link>
        </div>
        {lista.isLoading && <p className="text-[11px] text-muted-foreground">Cargando…</p>}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {(lista.data?.items ?? []).map((r) => (
            <TarjetaReplica key={r.id} r={r} />
          ))}
        </div>
        {lista.data && !lista.data.items.length && (
          <p className="text-[10px] text-muted-foreground">Aún no hay ninguna réplica registrada.</p>
        )}
      </Paso>
    </div>
  );
}

function FormularioAlta({
  modo,
  esAdmin,
  otros,
}: {
  modo: ModoReplicaVideo;
  esAdmin: boolean;
  otros: { username: string; nombre?: string }[];
}) {
  const registrar = useRegistrarReplicaVideo();
  const [file, setFile] = useState<File | null>(null);
  const [titulo, setTitulo] = useState("");
  const [productUrl, setProductUrl] = useState("");
  const [urlViral, setUrlViral] = useState("");
  const [tienda, setTienda] = useState("");
  const [caption, setCaption] = useState("");
  const [hashtags, setHashtags] = useState("");
  const [prompts, setPrompts] = useState("");
  const [para, setPara] = useState("");
  const [inputKey, setInputKey] = useState(0);

  const listo = Boolean(file && titulo.trim() && productUrl.trim());

  const enviar = () => {
    if (!file || !listo) return;
    registrar.mutate(
      {
        file, modo, titulo, product_url: productUrl, url_viral: urlViral, tienda, caption,
        hashtags, prompts, notas: "", para: esAdmin ? para : "",
      },
      {
        onSuccess: () => {
          toast.success(para && esAdmin ? `Registrado para ${para}: sale en sus tandas` : "Registrado: ya sale en Mis tandas");
          setFile(null);
          setInputKey((k) => k + 1);
          setTitulo("");
          setProductUrl("");
          setUrlViral("");
          setCaption("");
          setHashtags("");
          setPrompts("");
        },
        onError: (e) => toast.error(e.message),
      },
    );
  };

  return (
    <Paso
      n={1}
      color="violeta"
      titulo="Registra el vídeo montado"
      hint="El MP4 final (encuadre anti-marca, rótulo con el nombre del producto, metadatos limpios) + su enlace de TikTok Shop."
    >
      <input
        key={inputKey}
        type="file"
        accept="video/mp4,video/quicktime,.mp4,.mov"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="w-full text-[11px] file:mr-2 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-[11px]"
      />
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        <input value={titulo} onChange={(e) => setTitulo(e.target.value)} placeholder="Nombre del producto *" className={INPUT} />
        <input
          value={productUrl}
          onChange={(e) => setProductUrl(e.target.value)}
          placeholder="Enlace o ID de TikTok Shop *"
          className={INPUT}
        />
        <input value={urlViral} onChange={(e) => setUrlViral(e.target.value)} placeholder="Enlace del viral original" className={INPUT} />
        <input value={tienda} onChange={(e) => setTienda(e.target.value)} placeholder="Tienda" className={INPUT} />
      </div>
      <textarea value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Caption" rows={2} className={INPUT} />
      <input value={hashtags} onChange={(e) => setHashtags(e.target.value)} placeholder="#hashtags (uno por línea o separados)" className={INPUT} />
      <textarea
        value={prompts}
        onChange={(e) => setPrompts(e.target.value)}
        placeholder="Prompts usados (uno por línea), para poder rehacerlo"
        rows={2}
        className={INPUT}
      />
      {esAdmin && otros.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-[10px] text-muted-foreground">Para:</span>
          {[{ username: "", nombre: "Mí" }, ...otros].map((u) => (
            <button
              key={u.username || "yo"}
              type="button"
              onClick={() => setPara(u.username)}
              className={`rounded border px-2 py-1 text-[10px] ${
                para === u.username
                  ? "border-sky-500 bg-sky-500/10 text-sky-400"
                  : "border-border/60 text-muted-foreground hover:text-foreground"
              }`}
            >
              {u.nombre || u.username}
            </button>
          ))}
        </div>
      )}
      <button
        type="button"
        disabled={!listo || registrar.isPending}
        onClick={enviar}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40 sm:w-auto"
      >
        {registrar.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
        {registrar.isPending ? "Subiendo…" : "Registrar"}
      </button>
    </Paso>
  );
}

function TarjetaReplica({ r }: { r: ReplicaVideo }) {
  const borrar = useBorrarReplicaVideo();
  const estado = r.uploaded
    ? { t: "✓ Subido", c: "bg-emerald-500/20 text-emerald-400" }
    : r.rehacer
      ? { t: "🔁 Rehacer", c: "bg-red-500/20 text-red-400" }
      : r.sin_stock
        ? { t: "🚫 Sin stock", c: "bg-zinc-500/20 text-zinc-400" }
        : { t: "Pendiente", c: "bg-amber-500/20 text-amber-400" };
  return (
    <div className="space-y-1.5 rounded-xl border border-border/60 bg-background/40 p-2">
      <div className="flex items-start gap-1.5">
        <p className="min-w-0 flex-1 break-words text-[11px] font-semibold">{r.titulo}</p>
        <span className={`shrink-0 rounded px-1.5 py-px text-[9px] font-semibold ${MODOS_RV[r.modo] ?? ""}`}>
          {r.modo_label}
        </span>
      </div>
      {r.existe ? (
        <video
          src={urlVideoReplica(r)}
          controls
          preload="metadata"
          playsInline
          className="aspect-[9/16] max-h-72 w-full rounded-lg bg-black object-contain"
        />
      ) : (
        <p className="rounded-lg border border-amber-500/40 p-2 text-[10px] text-amber-400">El MP4 ya no está en el Drive.</p>
      )}
      {r.rehacer && r.rehacer_nota && (
        <p className="break-words text-[10px] text-red-400">{r.rehacer_nota}</p>
      )}
      <div className="flex flex-wrap items-center gap-1 text-[10px]">
        {r.product_url && (
          <a href={r.product_url} target="_blank" rel="noreferrer" className="truncate rounded border border-emerald-500/50 px-1.5 py-0.5 text-emerald-400">
            Producto
          </a>
        )}
        {r.url && (
          <a href={r.url} target="_blank" rel="noreferrer" className="truncate rounded border border-border/60 px-1.5 py-0.5 text-muted-foreground">
            Viral
          </a>
        )}
        {r.existe && (
          <a href={urlVideoReplica(r, true)} className="flex items-center gap-1 rounded border border-sky-500/50 px-1.5 py-0.5 text-sky-400">
            <Download className="h-3 w-3" /> MP4
          </a>
        )}
        <button
          type="button"
          disabled={borrar.isPending}
          onClick={() => {
            if (!window.confirm("¿Borrar esta réplica y su MP4? Sale también de Mis tandas.")) return;
            borrar.mutate(r.id, { onError: (e) => toast.error(e.message) });
          }}
          className="ml-auto flex items-center gap-1 rounded border border-border/60 px-1.5 py-0.5 text-muted-foreground hover:text-red-400"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
      <div className="flex items-center gap-1 border-t border-border/40 pt-1.5 text-[10px]">
        <span className={`rounded px-1.5 py-px font-semibold ${estado.c}`}>{estado.t}</span>
        {r.rehecho && <span className="text-muted-foreground">rehecho</span>}
        <span className="ml-auto text-muted-foreground">
          {new Date(r.creado_at * 1000).toLocaleDateString("es-ES", { day: "numeric", month: "short" })}
        </span>
      </div>
    </div>
  );
}
