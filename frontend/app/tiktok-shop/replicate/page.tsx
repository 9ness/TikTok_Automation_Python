"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Clapperboard,
  Copy,
  Download,
  Loader2,
  Upload,
} from "lucide-react";
import { toast } from "sonner";

import { useProducts, useProduct, productKeys } from "@/lib/queries/products";
import type { ProblemVideo } from "@/lib/queries/radar";

const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";

interface WhyViral {
  hook?: string;
  retention?: string;
  emotion?: string;
  why_sells?: string;
  visual_style?: string;
  structure?: string;
}

function CopyChip({ label, text, primary }: { label: string; text: string; primary?: boolean }) {
  if (!text) return null;
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        toast.success("Copiado");
      }}
      title={`Copiar: ${label}`}
      className={
        "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition " +
        (primary
          ? "border-purple-500/40 bg-purple-500/10 text-purple-500 hover:bg-purple-500/20"
          : "border-border text-muted-foreground hover:border-foreground/50 hover:text-foreground")
      }
    >
      <Copy className="h-3 w-3" /> {label}
    </button>
  );
}

export default function ReplicatePage() {
  const qc = useQueryClient();
  const { data: list, isLoading: loadingList } = useProducts({ limit: 200 });
  const products = useMemo(
    () => (list?.items ?? []).filter((p) => !p.deleted),
    [list],
  );

  const [productId, setProductId] = useState("");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [refFile, setRefFile] = useState<File | null>(null);
  const [n, setN] = useState(1);
  const [lang, setLang] = useState("es");
  const [generating, setGenerating] = useState(false);
  const [zoom, setZoom] = useState(1.18);

  const { data: product } = useProduct(productId || undefined);
  const replicas = (product?.viral_replicas ?? []) as ProblemVideo[];
  const why = (product?.viral_replica_analysis ?? {}) as WhyViral;

  // Subida / procesado por índice
  const [uploadingIdx, setUploadingIdx] = useState<number | null>(null);
  const [uploadPct, setUploadPct] = useState(0);
  const [processingIdx, setProcessingIdx] = useState<number | null>(null);

  const readyUrl = (i: number) =>
    `${apiBase}/api/v1/tiktok-shop/radar/videos/replica/ready?product_id=${productId}&concept_index=${i}` +
    (apiKey ? `&api_key=${encodeURIComponent(apiKey)}` : "");

  const generate = async () => {
    if (!productId) return toast.error("Elige un producto base.");
    if (!videoFile) return toast.error("Sube el vídeo viral a replicar.");
    setGenerating(true);
    const fd = new FormData();
    fd.append("file", videoFile);
    fd.append("product_id", productId);
    fd.append("n", String(n));
    fd.append("language", lang);
    if (refFile) fd.append("reference_photo", refFile);
    try {
      const res = await fetch(`${apiBase}/api/v1/tiktok-shop/radar/videos/replica/generate`, {
        method: "POST",
        headers: apiKey ? { "X-API-Key": apiKey } : undefined,
        body: fd,
      });
      const data = await res.json();
      if (data.ok && data.videos?.length) {
        toast.success(`${data.videos.length} versión(es) generadas${data.used_reference_photo ? " (con foto de referencia)" : ""}`);
        qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
      } else {
        toast.error(data.message ?? "No se pudo replicar.");
      }
    } catch (e) {
      toast.error(`Error: ${(e as Error).message}`);
    } finally {
      setGenerating(false);
    }
  };

  const uploadVideo = (i: number, f: File) => {
    setUploadingIdx(i);
    setUploadPct(0);
    const fd = new FormData();
    fd.append("file", f);
    fd.append("product_id", productId);
    fd.append("concept_index", String(i));
    fd.append("zoom", String(zoom));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiBase}/api/v1/tiktok-shop/radar/videos/replica/upload`);
    if (apiKey) xhr.setRequestHeader("X-API-Key", apiKey);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setUploadPct(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      setUploadingIdx(null);
      try {
        const data = JSON.parse(xhr.responseText);
        if (data.ok) {
          toast.success(data.message ?? "En la cola, procesando…");
          setProcessingIdx(i);
        } else toast.error(data.message ?? "Error procesando");
      } catch {
        toast.error("Respuesta inválida del servidor");
      }
    };
    xhr.onerror = () => {
      setUploadingIdx(null);
      toast.error("Error subiendo el vídeo");
    };
    xhr.send(fd);
  };

  // Polling hasta que aparezca ready_video del índice en proceso.
  useEffect(() => {
    if (processingIdx === null) return;
    const done = (product?.viral_replicas?.[processingIdx] as ProblemVideo | undefined)?.ready_video;
    if (done) {
      setProcessingIdx(null);
      toast.success("Réplica lista para descargar");
      return;
    }
    const t = setInterval(
      () => qc.invalidateQueries({ queryKey: productKeys.detail(productId) }),
      5000,
    );
    return () => clearInterval(t);
  }, [processingIdx, product, productId, qc]);

  const videoInputRef = useRef<HTMLInputElement>(null);
  const refInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-3 sm:p-4">
      <div className="flex items-center gap-2">
        <Clapperboard className="h-5 w-5 text-orange-500" />
        <h1 className="text-lg font-semibold">Replicar vídeo viral</h1>
      </div>
      <p className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
        Sube un vídeo que <b>ya funciona</b> en TikTok. Gemini analiza <b>por qué
        viraliza</b> y genera versiones <b>2 pasos (foto→vídeo)</b> para replicar la
        fórmula con <b>tu producto</b>. Copia el <b>Paso 1</b> en Nano Banana (adjunta la
        foto del producto) → la imagen resultante al <b>Paso 2</b> en Veo 3.1 → sube el
        vídeo aquí para quemar gancho + CTA + flecha.
      </p>

      {/* Formulario */}
      <div className="space-y-3 rounded-lg border border-border p-3">
        <div>
          <label className="mb-1 block text-xs font-medium">Producto base</label>
          <select
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
          >
            <option value="">{loadingList ? "Cargando…" : "— Elige un producto —"}</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <p className="mt-1 text-[10px] text-muted-foreground">
            La réplica llevará este producto. Sube una <b>foto de referencia</b> abajo solo
            si quieres trasladar la fórmula a un producto distinto al de sus fotos.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {/* Vídeo viral */}
          <div>
            <label className="mb-1 block text-xs font-medium">Vídeo viral (MP4) *</label>
            <input ref={videoInputRef} type="file" accept="video/*" className="hidden"
              onChange={(e) => { setVideoFile(e.target.files?.[0] ?? null); }} />
            <button
              onClick={() => videoInputRef.current?.click()}
              className="flex w-full items-center gap-2 truncate rounded-md border border-dashed border-border px-2 py-1.5 text-xs hover:border-foreground/50"
            >
              <Upload className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{videoFile ? videoFile.name : "Subir vídeo viral…"}</span>
            </button>
          </div>
          {/* Foto de referencia opcional */}
          <div>
            <label className="mb-1 block text-xs font-medium">Foto del producto (opcional)</label>
            <input ref={refInputRef} type="file" accept="image/*" className="hidden"
              onChange={(e) => { setRefFile(e.target.files?.[0] ?? null); }} />
            <button
              onClick={() => refInputRef.current?.click()}
              className="flex w-full items-center gap-2 truncate rounded-md border border-dashed border-border px-2 py-1.5 text-xs hover:border-foreground/50"
            >
              <Upload className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{refFile ? refFile.name : "Foto de referencia…"}</span>
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium">Versiones:</span>
            <select value={n} onChange={(e) => setN(+e.target.value)}
              className="rounded-md border border-border bg-background px-2 py-0.5 text-xs">
              <option value={1}>1 (fiel)</option>
              <option value={2}>2</option>
              <option value={3}>3</option>
            </select>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium">Idioma:</span>
            <select value={lang} onChange={(e) => setLang(e.target.value)}
              className="rounded-md border border-border bg-background px-2 py-0.5 text-xs">
              <option value="es">🇪🇸 Español</option>
              <option value="en">🇬🇧 English</option>
            </select>
          </div>
          <button
            disabled={generating}
            onClick={generate}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md bg-orange-500 px-3 py-1.5 text-sm font-semibold text-white hover:bg-orange-600 disabled:opacity-50"
          >
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Clapperboard className="h-4 w-4" />}
            {generating ? "Analizando…" : "Analizar y replicar"}
          </button>
        </div>
        {generating && (
          <p className="text-[11px] text-muted-foreground">
            Extrayendo audio (Whisper) + muestreando frames + Gemini… puede tardar ~30-60s.
          </p>
        )}
      </div>

      {/* Por qué viraliza */}
      {(why.hook || why.structure) && (
        <div className="space-y-1.5 rounded-lg border border-border p-3">
          <h2 className="text-sm font-semibold">🔍 Por qué viraliza</h2>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {why.hook && <li><b className="text-foreground">Gancho:</b> {why.hook}</li>}
            {why.retention && <li><b className="text-foreground">Retención:</b> {why.retention}</li>}
            {why.emotion && <li><b className="text-foreground">Emoción:</b> {why.emotion}</li>}
            {why.why_sells && <li><b className="text-foreground">Por qué vende:</b> {why.why_sells}</li>}
            {why.visual_style && <li><b className="text-foreground">Estilo visual:</b> {why.visual_style}</li>}
            {why.structure && <li><b className="text-foreground">Estructura:</b> {why.structure}</li>}
          </ul>
        </div>
      )}

      {/* Réplicas */}
      {replicas.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 rounded bg-muted/40 p-2 text-[11px]">
            <span>🔍 Zoom quita-marca:</span>
            <input type="range" min={1} max={1.4} step={0.02} value={zoom}
              onChange={(e) => setZoom(+e.target.value)} className="h-1 w-32" />
            <span className="font-mono">{zoom.toFixed(2)}×</span>
            <span className="text-muted-foreground">(sube si aún se ve la marca; aplica al subir)</span>
          </div>
          {replicas.map((v, i) => {
            const fileInput = (
              <input type="file" accept="video/*" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadVideo(i, f); e.target.value = ""; }} />
            );
            const actionBtn =
              uploadingIdx === i ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-orange-500">
                  <Loader2 className="h-3 w-3 animate-spin" /> {uploadPct}%
                </span>
              ) : processingIdx === i ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-orange-500">
                  <Loader2 className="h-3 w-3 animate-spin" /> en cola…
                </span>
              ) : v.ready_video ? (
                <div className="flex items-center gap-1.5">
                  <a href={readyUrl(i)} download
                    className="inline-flex items-center gap-1 rounded-md bg-green-600 px-2.5 py-1.5 text-[11px] font-semibold text-white">
                    <Download className="h-3.5 w-3.5" /> Descargar
                  </a>
                  <label className="cursor-pointer text-[10px] text-muted-foreground hover:underline" title="re-subir">
                    {fileInput}↻
                  </label>
                </div>
              ) : (
                <label className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-orange-500 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-orange-600">
                  {fileInput}📤 Subir vídeo
                </label>
              );
            return (
              <div key={i} className="rounded-lg border border-border/60 p-2.5 text-xs">
                <div className="mb-1.5 flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="font-semibold">R{i + 1}</span>{" "}
                    <span className="text-muted-foreground">{v.concept}</span>
                    {v.format && (
                      <span className="ml-1 inline-block rounded bg-orange-500/10 px-1.5 py-0.5 text-[10px] text-orange-600">
                        {v.format}
                      </span>
                    )}
                  </div>
                  <div className="shrink-0">{actionBtn}</div>
                </div>
                {v.angle && <p className="mb-1.5 text-[11px] text-muted-foreground">{v.angle}</p>}
                <div className="flex flex-wrap gap-1.5">
                  <CopyChip label="🖼️ Paso 1 imagen" text={v.image_prompt ?? ""} primary />
                  <CopyChip label="🎬 Paso 2 animar" text={v.animate_prompt ?? ""} primary />
                  <CopyChip label="📌 Gancho" text={v.hook_text} />
                  <CopyChip label="🛒 CTA" text={v.cta_text} />
                  <CopyChip label="✍️ Caption" text={v.caption} />
                  {v.spoken_line && <CopyChip label="🗣️ Voz" text={v.spoken_line} />}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
