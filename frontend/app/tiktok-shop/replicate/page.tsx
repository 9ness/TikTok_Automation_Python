"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Clapperboard,
  Copy,
  Download,
  Loader2,
  Trash2,
  Upload,
} from "lucide-react";
import { toast } from "sonner";

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
  shots?: string;
  human_presence?: string;
  person_gender?: string;
  cta_action?: string;
}

const PRESENCE_LABEL: Record<string, string> = {
  none: "Sin personas (solo producto)",
  hands_only: "POV — solo manos (sin cara)",
  body_no_face: "Cuerpo sin cara",
  face: "Persona con cara",
};

const GENDER_LABEL: Record<string, string> = {
  male: "Masculino",
  female: "Femenino",
  none: "Sin persona/voz",
};

interface ReplicaResult {
  videos: ProblemVideo[];
  why: WhyViral;
  mode: string;
  productName: string;
  hasThumb: boolean;
}

interface HistoryItem {
  id: string;
  title: string;
  product_name?: string;
  has_thumb?: boolean;
  mode: string;
  n_versions: number;
  n_ready: number;
  duration_s: number;
  created_at: string;
}

const thumbUrl = (id: string) =>
  `${apiBase}/api/v1/tiktok-shop/radar/videos/replica/thumb?replica_id=${id}` +
  (apiKey ? `&api_key=${encodeURIComponent(apiKey)}` : "");

async function apiFetch(path: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  if (apiKey) headers.set("X-API-Key", apiKey);
  const res = await fetch(`${apiBase}${path}`, { ...init, headers });
  return res.json();
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
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [refFile, setRefFile] = useState<File | null>(null);
  const [sameProduct, setSameProduct] = useState(true);
  const [n, setN] = useState(1);
  const [lang, setLang] = useState("es");
  const [generating, setGenerating] = useState(false);
  const [zoom, setZoom] = useState(1.18);
  const [result, setResult] = useState<ReplicaResult | null>(null);
  const [replicaId, setReplicaId] = useState<string | null>(null);

  // Historial de réplicas guardadas.
  const [history, setHistory] = useState<HistoryItem[]>([]);

  // Estado de subida→edición por índice de tarjeta (editor genérico por token).
  const [uploadingIdx, setUploadingIdx] = useState<number | null>(null);
  const [uploadPct, setUploadPct] = useState(0);
  const [processingIdx, setProcessingIdx] = useState<number | null>(null);
  const [tokens, setTokens] = useState<Record<number, string>>({});

  const loadHistory = useCallback(async () => {
    try {
      const d = await apiFetch("/api/v1/tiktok-shop/radar/videos/replica/list");
      if (d.ok) setHistory(d.items ?? []);
    } catch {
      /* silencioso */
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // Al cargar unos `videos`, inicializa los tokens de los ya quemados.
  const seedTokens = (vids: ProblemVideo[]) => {
    const t: Record<number, string> = {};
    vids.forEach((v, i) => {
      if (v.ready_token) t[i] = v.ready_token;
    });
    setTokens(t);
  };

  const loadSession = async (id: string) => {
    const d = await apiFetch(`/api/v1/tiktok-shop/radar/videos/replica/get?replica_id=${id}`);
    if (d.ok) {
      setResult({
        videos: d.videos ?? [], why: d.why_viral ?? {}, mode: d.mode ?? "versions",
        productName: d.product_name ?? "", hasThumb: !!d.has_thumb,
      });
      setReplicaId(id);
      seedTokens(d.videos ?? []);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else toast.error(d.message ?? "No se pudo cargar.");
  };

  const deleteSession = async (id: string) => {
    const d = await apiFetch(`/api/v1/tiktok-shop/radar/videos/replica/delete?replica_id=${id}`, { method: "DELETE" });
    if (d.ok) {
      toast.success("Réplica borrada");
      if (replicaId === id) {
        setResult(null);
        setReplicaId(null);
      }
      loadHistory();
    } else toast.error("No se pudo borrar.");
  };

  const videoInputRef = useRef<HTMLInputElement>(null);
  const refInputRef = useRef<HTMLInputElement>(null);

  const readyUrl = (token: string) =>
    `${apiBase}/api/v1/tiktok-shop/radar/videos/edit/ready?token=${token}` +
    (apiKey ? `&api_key=${encodeURIComponent(apiKey)}` : "");

  const generate = async () => {
    if (!videoFile) return toast.error("Sube el vídeo viral a replicar.");
    if (!refFile) return toast.error("Sube la foto del producto.");
    setGenerating(true);
    setResult(null);
    setTokens({});
    const fd = new FormData();
    fd.append("file", videoFile);
    fd.append("reference_photo", refFile);
    fd.append("same_product", String(sameProduct));
    fd.append("n", String(n));
    fd.append("language", lang);
    try {
      const res = await fetch(`${apiBase}/api/v1/tiktok-shop/radar/videos/replica/generate`, {
        method: "POST",
        headers: apiKey ? { "X-API-Key": apiKey } : undefined,
        body: fd,
      });
      const data = await res.json();
      if (data.ok && data.videos?.length) {
        setResult({
          videos: data.videos, why: data.why_viral ?? {}, mode: data.mode ?? "versions",
          productName: data.product_name ?? "", hasThumb: !!data.has_thumb,
        });
        setReplicaId(data.replica_id ?? null);
        toast.success(`${data.videos.length} ${data.mode === "segments" ? "réplica (troceada)" : "versión(es)"} lista(s) · guardada`);
        loadHistory();
      } else {
        toast.error(data.message ?? "No se pudo replicar.");
      }
    } catch (e) {
      toast.error(`Error: ${(e as Error).message}`);
    } finally {
      setGenerating(false);
    }
  };

  const pollStatus = (i: number, token: string) => {
    const t = setInterval(async () => {
      try {
        const r = await fetch(
          `${apiBase}/api/v1/tiktok-shop/radar/videos/edit/status?token=${token}` +
            (apiKey ? `&api_key=${encodeURIComponent(apiKey)}` : ""),
          { headers: apiKey ? { "X-API-Key": apiKey } : undefined },
        );
        const d = await r.json();
        if (d.ready) {
          clearInterval(t);
          setProcessingIdx((cur) => (cur === i ? null : cur));
          setTokens((prev) => ({ ...prev, [i]: token }));
          toast.success("Vídeo listo para descargar");
          // Persistir el token en la sesión → sobrevive recargas.
          if (replicaId) {
            apiFetch("/api/v1/tiktok-shop/radar/videos/replica/settoken", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ replica_id: replicaId, concept_index: i, token }),
            }).then(() => loadHistory()).catch(() => undefined);
          }
        }
      } catch {
        /* reintenta en el siguiente tick */
      }
    }, 5000);
  };

  const uploadVideo = (i: number, f: File, hookText: string, ctaText: string) => {
    setUploadingIdx(i);
    setUploadPct(0);
    const fd = new FormData();
    fd.append("file", f);
    fd.append("hook_text", hookText);
    fd.append("cta_text", ctaText);
    fd.append("zoom", String(zoom));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiBase}/api/v1/tiktok-shop/radar/videos/edit/upload`);
    if (apiKey) xhr.setRequestHeader("X-API-Key", apiKey);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setUploadPct(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      setUploadingIdx(null);
      try {
        const data = JSON.parse(xhr.responseText);
        if (data.ok && data.token) {
          toast.success(data.message ?? "En la cola, procesando…");
          setProcessingIdx(i);
          setTokens((prev) => {
            const next = { ...prev };
            delete next[i];
            return next;
          });
          pollStatus(i, data.token);
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

  const why = result?.why ?? {};
  const videos = result?.videos ?? [];

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-3 sm:p-4">
      <div className="flex items-center gap-2">
        <Clapperboard className="h-5 w-5 text-orange-500" />
        <h1 className="text-lg font-semibold">Replicar vídeo viral</h1>
      </div>
      <p className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
        Sube un vídeo que <b>ya funciona</b> + la <b>foto del producto</b>. Gemini analiza
        <b> por qué viraliza</b> y genera versiones <b>2 pasos (foto→vídeo)</b>. Copia el
        <b> Paso 1</b> en Nano Banana (adjunta la foto) → la imagen al <b>Paso 2</b> en Veo 3.1
        → sube el vídeo aquí para quemar gancho + CTA + flecha. <b>No hace falta crear el
        producto en la web.</b>
      </p>

      {/* Formulario */}
      <div className="space-y-3 rounded-lg border border-border p-3">
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
          {/* Foto del producto */}
          <div>
            <label className="mb-1 block text-xs font-medium">Foto del producto *</label>
            <input ref={refInputRef} type="file" accept="image/*" className="hidden"
              onChange={(e) => { setRefFile(e.target.files?.[0] ?? null); }} />
            <button
              onClick={() => refInputRef.current?.click()}
              className="flex w-full items-center gap-2 truncate rounded-md border border-dashed border-border px-2 py-1.5 text-xs hover:border-foreground/50"
            >
              <Upload className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{refFile ? refFile.name : "Subir foto del producto…"}</span>
            </button>
          </div>
        </div>

        {/* Check: ¿la foto es el producto del vídeo? */}
        <label className="flex cursor-pointer items-start gap-2 rounded-md bg-muted/40 p-2 text-xs">
          <input type="checkbox" checked={sameProduct}
            onChange={(e) => setSameProduct(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-orange-500" />
          <span>
            <b>La foto es el mismo producto que sale en el vídeo.</b>
            <span className="block text-[10px] text-muted-foreground">
              Desmárcalo si es <b>tu producto distinto</b> y solo quieres trasladar la fórmula
              del viral a él.
            </span>
          </span>
        </label>

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
        <p className="text-[10px] text-muted-foreground">
          Vídeos &gt;10s se trocean solos en clips de ~8s encadenados. El análisis tarda ~30-60s
          (Whisper + Gemini).
        </p>
      </div>

      {/* Cabecera del resultado: producto + miniatura */}
      {result && (result.productName || result.hasThumb) && (
        <div className="flex items-center gap-3 rounded-lg border border-orange-500/40 bg-orange-500/5 p-2.5">
          {result.hasThumb && replicaId && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={thumbUrl(replicaId)} alt="" className="h-14 w-14 shrink-0 rounded-md border border-border object-cover" />
          )}
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Producto</div>
            <div className="truncate text-sm font-semibold">{result.productName || "(sin nombre)"}</div>
          </div>
        </div>
      )}

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
            {why.human_presence && (
              <li>
                <b className="text-foreground">Personas:</b> {PRESENCE_LABEL[why.human_presence] ?? why.human_presence}
                {why.person_gender && why.person_gender !== "none" && (
                  <> · {GENDER_LABEL[why.person_gender] ?? why.person_gender}</>
                )}
              </li>
            )}
            {why.shots && <li><b className="text-foreground">Planos:</b> {why.shots}</li>}
            {why.cta_action && why.cta_action !== "none" && (
              <li><b className="text-foreground">Gesto CTA:</b> {why.cta_action}</li>
            )}
            {why.structure && <li><b className="text-foreground">Estructura:</b> {why.structure}</li>}
          </ul>
        </div>
      )}

      {/* Réplicas */}
      {videos.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 rounded bg-muted/40 p-2 text-[11px]">
            <span>🔍 Zoom quita-marca:</span>
            <input type="range" min={1} max={1.4} step={0.02} value={zoom}
              onChange={(e) => setZoom(+e.target.value)} className="h-1 w-32" />
            <span className="font-mono">{zoom.toFixed(2)}×</span>
            <span className="text-muted-foreground">(sube si aún se ve la marca; aplica al subir)</span>
          </div>
          {videos.map((v, i) => {
            const doneToken = tokens[i];
            const fileInput = (
              <input type="file" accept="video/*" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadVideo(i, f, v.hook_text, v.cta_text); e.target.value = ""; }} />
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
              ) : doneToken ? (
                <div className="flex items-center gap-1.5">
                  <a href={readyUrl(doneToken)} download
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
                    <span className="font-semibold">{result?.mode === "segments" ? "Réplica" : `V${i + 1}`}</span>{" "}
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

                {v.segments && v.segments.length > 0 ? (
                  <>
                    <p className="mb-1.5 rounded bg-muted/50 p-1.5 text-[10px] text-muted-foreground">
                      🎬 Es largo, se replica en <b>{v.segments.length} clips</b> que unes al final.
                      <b> Cada trozo tiene su propia foto</b> (la persona sale SIEMPRE en la foto).
                      Para que sea la <b>misma persona</b>: en el trozo 1 generas la foto con la del
                      producto; en los siguientes, <b>adjunta la foto del trozo anterior + la del
                      producto</b> → Nano Banana mantiene la cara. Luego animas cada foto en Veo 3.1
                      y unes los clips en orden.
                    </p>
                    <div className="space-y-1.5">
                      {v.segments.map((s, si) => {
                        const isScene = si > 0 && s.transition === "cut";
                        return (
                          <div key={si} className="rounded border border-border/50 p-1.5">
                            <div className="mb-1 text-[11px] font-medium">
                              {si === 0 ? "🎬" : isScene ? "✂️" : "🔗"} {s.label}
                              <span className="ml-1 text-[10px] font-normal text-muted-foreground">
                                {si === 0
                                  ? "(foto de apertura: persona + producto)"
                                  : isScene
                                    ? "(cambio de escena — genera foto nueva adjuntando la anterior + producto, MISMA persona)"
                                    : "(misma persona: adjunta la foto del trozo anterior + la del producto)"}
                              </span>
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              <CopyChip label={si === 0 ? "🖼️ Foto (Paso 1)" : "🖼️ Foto (misma persona)"} text={s.image_prompt} primary />
                              <CopyChip label="🎬 Animar (Paso 2)" text={s.animate_prompt} primary />
                              {s.spoken_line && <CopyChip label="🗣️ Voz (este trozo)" text={s.spoken_line} />}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      <CopyChip label="📌 Gancho" text={v.hook_text} />
                      <CopyChip label="🛒 CTA" text={v.cta_text} />
                      <CopyChip label="✍️ Caption" text={v.caption} />
                    </div>
                  </>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    <CopyChip label="🖼️ Paso 1 imagen" text={v.image_prompt ?? ""} primary />
                    <CopyChip label="🎬 Paso 2 animar" text={v.animate_prompt ?? ""} primary />
                    <CopyChip label="📌 Gancho" text={v.hook_text} />
                    <CopyChip label="🛒 CTA" text={v.cta_text} />
                    <CopyChip label="✍️ Caption" text={v.caption} />
                    {v.spoken_line && <CopyChip label="🗣️ Voz" text={v.spoken_line} />}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Historial de réplicas guardadas */}
      {history.length > 0 && (
        <div className="space-y-1.5 rounded-lg border border-border p-3">
          <h2 className="text-sm font-semibold">🗂️ Mis réplicas guardadas ({history.length})</h2>
          <p className="text-[10px] text-muted-foreground">
            Cada réplica que generas se guarda aquí. Ábrela para volver a copiar los prompts
            o descargar el vídeo quemado. No se pierden al recargar.
          </p>
          <div className="space-y-1.5">
            {history.map((h) => (
              <div
                key={h.id}
                className={
                  "flex items-center gap-2 rounded-md border p-2 text-xs " +
                  (replicaId === h.id ? "border-orange-500/60 bg-orange-500/5" : "border-border/60")
                }
              >
                <button onClick={() => loadSession(h.id)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                  {h.has_thumb ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={thumbUrl(h.id)} alt="" className="h-10 w-10 shrink-0 rounded border border-border object-cover" />
                  ) : (
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded border border-border text-muted-foreground">🎬</div>
                  )}
                  <div className="min-w-0">
                    <div className="truncate font-medium">{h.product_name || h.title}</div>
                    <div className="text-[10px] text-muted-foreground">
                      {h.mode === "segments" ? "🎬 troceada" : `${h.n_versions} versión(es)`}
                      {" · "}{Math.round(h.duration_s)}s
                      {h.n_ready > 0 && <span className="text-green-600"> · {h.n_ready} listo(s) ✅</span>}
                      {" · "}{new Date(h.created_at).toLocaleDateString()}
                    </div>
                  </div>
                </button>
                <button
                  onClick={() => deleteSession(h.id)}
                  title="Borrar"
                  className="shrink-0 rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
