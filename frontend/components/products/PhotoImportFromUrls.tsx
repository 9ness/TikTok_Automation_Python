"use client";

import { useState } from "react";
import {
  AlertTriangle,
  Check,
  ExternalLink,
  Loader2,
  Search,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useCommitImportedPhotos,
  useImportPhotosFromUrls,
  useSearchPhotosOnGoogle,
} from "@/lib/queries/products";
import type {
  PhotoCandidateGrade,
  PhotoType,
  Product,
} from "@/lib/types/product";
import { cn } from "@/lib/utils";

const PHOTO_TYPES: PhotoType[] = ["packshot", "lifestyle", "detail", "in_use", "macro"];

/** El backend devuelve preview_url RELATIVO (ej. /api/v1/products/...).
 *  Como el frontend corre en :3000 y la API en :8000, hay que prefijar
 *  igual que en `pickCoverPhotoUrl` del ProductCard. */
function buildPreviewUrl(relative: string): string {
  if (!relative) return "";
  if (relative.startsWith("http://") || relative.startsWith("https://")) {
    return relative;
  }
  const base = api.baseUrl;
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `?api_key=${encodeURIComponent(key)}` : "";
  return `${base}${relative}${qs}`;
}

/** Default search query — evita duplicar la marca si el name ya empieza con ella.
 *  Caso real: brand="Freshly", name="Freshly - Crema..." → "Freshly Freshly..."
 *  se vuelve solo "Freshly - Crema...". */
function buildDefaultSearchQuery(product: Product): string {
  const brand = (product.brand || "").trim();
  const name = (product.name || "").trim();
  if (!brand && !name) return "Marca + nombre producto";
  if (!brand) return name;
  if (!name) return brand;
  const brandLc = brand.toLowerCase();
  if (name.toLowerCase().startsWith(brandLc)) {
    return name;
  }
  return `${brand} ${name}`;
}

function scoreColor(score: number): string {
  if (score >= 8) return "bg-emerald-500 text-white";
  if (score >= 6) return "bg-sky-500 text-white";
  if (score >= 4) return "bg-amber-500 text-black";
  return "bg-rose-500 text-white";
}

function scoreLabel(score: number): string {
  if (score >= 8) return "Excelente";
  if (score >= 6) return "Buena";
  if (score >= 4) return "Aceptable";
  return "Mala";
}

/** Sección para buscar/importar fotos del producto desde URLs externas.
 *  Flujo:
 *  1. (opcional) Botón "Buscar en Google" — si CSE configurado autorellena
 *     la textarea con 10 URLs de Google Images.
 *  2. User edita la textarea (puede pegar más URLs manualmente).
 *  3. Click "Analizar" → backend descarga cada una y Gemini la puntúa.
 *  4. Grid de candidatas con score 0-10 + flags (texto, watermark, …).
 *  5. User marca cuáles guardar + elige tipo (packshot/lifestyle/…).
 *  6. Click "Guardar seleccionadas" → backend persiste como fotos source. */
export function PhotoImportFromUrls({ product }: { product: Product }) {
  const importMut = useImportPhotosFromUrls(product.id);
  const commitMut = useCommitImportedPhotos(product.id);
  const searchMut = useSearchPhotosOnGoogle(product.id);

  const [urlsText, setUrlsText] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [candidates, setCandidates] = useState<PhotoCandidateGrade[]>([]);
  // Por candidate_id → si está marcado para guardar + qué tipo final
  const [keep, setKeep] = useState<Record<string, boolean>>({});
  const [typeOverride, setTypeOverride] = useState<Record<string, PhotoType>>({});

  // ¿Tenemos foto packshot guardada? Si sí, Gemini compara y detecta
  // productos diferentes. Lo mostramos como hint en la UI.
  const hasReferencePhotos = product.photos.source.some(
    (p) => !p.deleted && p.local_path,
  );

  async function handleSearch() {
    try {
      const r = await searchMut.mutateAsync({
        query: searchQuery.trim() || undefined,
        num: 10,
        provider: "auto",
      });
      if (r.results.length === 0) {
        toast.info(r.hint || `Sin resultados para "${r.query_used}".`);
        return;
      }
      // Añade las URLs al final de lo que ya hubiera (sin duplicar)
      setUrlsText((current) => {
        const existing = new Set(
          current
            .split(/\r?\n/)
            .map((l) => l.trim())
            .filter(Boolean),
        );
        const additions = r.results
          .map((x) => x.link)
          .filter((u) => !existing.has(u));
        if (additions.length === 0) return current;
        const sep = current.trim() ? "\n" : "";
        return current + sep + additions.join("\n");
      });
      const providerLabel =
        r.provider_used === "google_cse" ? "Google" : "DuckDuckGo";
      toast.success(
        `${r.results.length} URLs añadidas (${providerLabel} · "${r.query_used}")`,
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Búsqueda falló");
    }
  }

  async function handleAnalyze() {
    const urls = urlsText
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => l.startsWith("http"));
    if (urls.length === 0) {
      toast.error("Pega al menos una URL http(s)");
      return;
    }
    if (urls.length > 20) {
      toast.error("Máximo 20 URLs por análisis");
      return;
    }
    try {
      const r = await importMut.mutateAsync({ urls });
      setCandidates(r.candidates);
      // Pre-marca TOP 3 COMPLEMENTARIAS:
      // - filtrar válidas (score >= 6, sin error, mismo producto, no duplicado)
      // - ordenar por score desc + preferir tipos DISTINTOS entre ellas
      const initialKeep: Record<string, boolean> = {};
      const initialType: Record<string, PhotoType> = {};
      const valid = r.candidates
        .filter(
          (c) =>
            c.score >= 6 &&
            !c.error &&
            c.is_same_product &&
            !c.is_duplicate_of_reference,
        )
        .sort((a, b) => b.score - a.score);

      // Greedy: ir cogiendo la siguiente con mejor score cuyo `type`
      // todavía no esté en el set elegido. Si solo queda un tipo,
      // permite repetir hasta llegar a 3.
      const chosenTypes = new Set<string>();
      const chosenIds = new Set<string>();
      // Primera pasada: tipos únicos
      for (const c of valid) {
        if (chosenIds.size >= 3) break;
        if (!chosenTypes.has(c.type)) {
          chosenIds.add(c.candidate_id);
          chosenTypes.add(c.type);
        }
      }
      // Segunda pasada: rellenar hasta 3 con las que queden por score
      for (const c of valid) {
        if (chosenIds.size >= 3) break;
        chosenIds.add(c.candidate_id);
      }

      for (const c of r.candidates) {
        initialKeep[c.candidate_id] = chosenIds.has(c.candidate_id);
        if (c.type !== "other") {
          initialType[c.candidate_id] = c.type as PhotoType;
        }
      }
      setKeep(initialKeep);
      setTypeOverride(initialType);
      const validCount = valid.length;
      const dupCount = r.candidates.filter(
        (c) => c.is_duplicate_of_reference && !c.error,
      ).length;
      const differentCount = r.candidates.filter(
        (c) => !c.is_same_product && !c.error,
      ).length;
      const parts = [
        `${r.candidates.length} fotos analizadas`,
        `${chosenIds.size} pre-marcadas (top 3)`,
        `${validCount} válidas total`,
      ];
      if (dupCount > 0) parts.push(`${dupCount} duplicado`);
      if (differentCount > 0) parts.push(`${differentCount} producto distinto`);
      toast.success(parts.join(" · "));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Análisis falló");
    }
  }

  async function handleCommit() {
    const selected = candidates.filter((c) => keep[c.candidate_id] && !c.error);
    if (selected.length === 0) {
      toast.error("Marca al menos una foto para guardar");
      return;
    }
    try {
      const r = await commitMut.mutateAsync({
        candidates: selected.map((c) => ({
          candidate_id: c.candidate_id,
          type:
            typeOverride[c.candidate_id] ||
            (c.type !== "other" ? (c.type as PhotoType) : "packshot"),
        })),
      });
      toast.success(`${r.saved_count} fotos guardadas en source`);
      // Limpiar para el siguiente lote
      setCandidates([]);
      setKeep({});
      setTypeOverride({});
      setUrlsText("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Guardar falló");
    }
  }

  const selectedCount = candidates.filter(
    (c) => keep[c.candidate_id] && !c.error,
  ).length;

  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-emerald-500" />
            <h3 className="text-sm font-semibold">Importar fotos por URL</h3>
          </div>
          <p className="text-xs text-muted-foreground">
            Busca con un click (DuckDuckGo) o pega URLs a mano. Gemini Vision
            las puntúa 0-10, detecta tipo y
            {hasReferencePhotos ? (
              <>
                {" "}
                <strong className="text-emerald-700 dark:text-emerald-400">
                  compara con las fotos guardadas
                </strong>{" "}
                — descarta productos distintos y marca duplicados (mismo plano
                que ya tienes).
              </>
            ) : (
              <>
                {" "}
                problemas (texto, watermark, collage). Tip: guarda primero una
                foto del producto (la del scrape de URL TikTok Shop sirve) y la
                siguiente vuelta detectará productos distintos.
              </>
            )}
            <br />
            <span className="text-emerald-700 dark:text-emerald-400">
              Objetivo:{" "}
              <strong>3 fotos COMPLEMENTARIAS</strong> (packshot + lifestyle +
              detail/macro), no clones del mismo plano. Standard tier acepta
              hasta 3 referencias por vídeo.
            </span>
          </p>
        </div>

        {/* Buscador automático (DuckDuckGo, sin API key) */}
        <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 p-2 space-y-2">
          <Label htmlFor="search-q" className="text-[11px]">
            Buscar fotos automáticamente
          </Label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              id="search-q"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={buildDefaultSearchQuery(product)}
              className="flex-1 text-sm"
            />
            <Button
              type="button"
              variant="outline"
              onClick={handleSearch}
              disabled={searchMut.isPending}
              className="shrink-0"
            >
              {searchMut.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              <span className="ml-2">Buscar</span>
            </Button>
          </div>
          <p className="text-[10px] text-muted-foreground">
            Vacío usa <code>{product.brand} {product.name}</code>. Añade
            atributos diferenciadores (color, modelo) si la marca tiene productos
            parecidos — luego Gemini igualmente filtra los que no cuadren.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="urls-input" className="text-xs">
            URLs (una por línea, máx 20)
          </Label>
          <Textarea
            id="urls-input"
            value={urlsText}
            onChange={(e) => setUrlsText(e.target.value)}
            placeholder={"https://...\nhttps://...\nhttps://..."}
            rows={5}
            className="font-mono text-[11px]"
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            onClick={handleAnalyze}
            disabled={importMut.isPending || !urlsText.trim()}
          >
            {importMut.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Wand2 className="mr-2 h-4 w-4" />
            )}
            Analizar URLs
          </Button>
          {candidates.length > 0 && (
            <Button
              type="button"
              variant="default"
              onClick={handleCommit}
              disabled={commitMut.isPending || selectedCount === 0}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {commitMut.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Check className="mr-2 h-4 w-4" />
              )}
              Guardar seleccionadas ({selectedCount})
            </Button>
          )}
        </div>

        {/* Grid de candidatas con score + flags + select tipo */}
        {candidates.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {candidates.map((c) => {
              const checked = keep[c.candidate_id] ?? false;
              const tp = typeOverride[c.candidate_id] || c.type;
              const flags: string[] = [];
              if (c.has_text_overlay) flags.push("texto");
              if (c.has_watermark) flags.push("watermark");
              if (c.is_collage) flags.push("collage");
              if (c.is_branded) flags.push("marca");
              if (c.is_duplicate_of_reference) flags.push("duplicado");
              const isDifferent =
                !c.is_same_product &&
                c.same_product_confidence !== "no_reference";
              const isDuplicate = c.is_duplicate_of_reference;
              return (
                <div
                  key={c.candidate_id}
                  className={cn(
                    "relative overflow-hidden rounded-lg border-2 transition-colors",
                    c.error
                      ? "border-rose-500/30 opacity-60"
                      : isDifferent
                        ? "border-rose-500/60 bg-rose-500/5"
                        : isDuplicate
                          ? "border-amber-500/60 bg-amber-500/5"
                          : checked
                            ? "border-emerald-500"
                            : "border-muted",
                  )}
                >
                  {/* Preview */}
                  <div
                    className="relative aspect-square cursor-pointer bg-muted"
                    onClick={() =>
                      !c.error &&
                      setKeep((k) => ({ ...k, [c.candidate_id]: !checked }))
                    }
                  >
                    {!c.error ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={buildPreviewUrl(c.preview_url)}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center p-3 text-center">
                        <AlertTriangle className="mx-auto h-6 w-6 text-rose-500" />
                      </div>
                    )}
                    {/* Score badge top-left */}
                    {!c.error && (
                      <div
                        className={cn(
                          "absolute left-2 top-2 rounded-md px-2 py-0.5 text-xs font-bold",
                          scoreColor(c.score),
                        )}
                        title={`${scoreLabel(c.score)} — ${c.reasons}`}
                      >
                        {c.score}/10
                      </div>
                    )}
                    {/* Badge "producto diferente" top-center si Gemini lo
                        detectó comparando con la foto packshot guardada */}
                    {isDifferent && !c.error && (
                      <div
                        className="absolute left-1/2 top-2 -translate-x-1/2 rounded-md bg-rose-600 px-2 py-0.5 text-[10px] font-bold text-white shadow"
                        title={c.reasons}
                      >
                        ✕ producto distinto
                      </div>
                    )}
                    {/* Badge "duplicado" si la candidata es esencialmente
                        el mismo plano que una foto de referencia. */}
                    {isDuplicate && !isDifferent && !c.error && (
                      <div
                        className="absolute left-1/2 top-2 -translate-x-1/2 rounded-md bg-amber-600 px-2 py-0.5 text-[10px] font-bold text-white shadow"
                        title={c.reasons}
                      >
                        ⇄ duplicado
                      </div>
                    )}
                    {/* Checkbox top-right */}
                    {!c.error && (
                      <div
                        className={cn(
                          "absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full border-2",
                          checked
                            ? "border-emerald-500 bg-emerald-500"
                            : "border-white bg-white/30 backdrop-blur-sm",
                        )}
                      >
                        {checked && <Check className="h-3.5 w-3.5 text-white" />}
                      </div>
                    )}
                    {/* Flags badges bottom */}
                    {flags.length > 0 && !c.error && (
                      <div className="absolute bottom-1 left-1 flex flex-wrap gap-1">
                        {flags.map((f) => (
                          <span
                            key={f}
                            className="rounded bg-black/70 px-1.5 py-0.5 text-[9px] text-white"
                          >
                            {f}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Body */}
                  <div className="space-y-1.5 p-2">
                    {c.error ? (
                      <p className="text-[10px] text-rose-600 dark:text-rose-400">
                        {c.error}
                      </p>
                    ) : (
                      <>
                        <p
                          className="line-clamp-2 text-[10px] text-muted-foreground"
                          title={c.reasons}
                        >
                          {c.reasons}
                        </p>
                        <div className="flex items-center gap-1">
                          <Select
                            value={tp as string}
                            onValueChange={(v) =>
                              setTypeOverride((to) => ({
                                ...to,
                                [c.candidate_id]: v as PhotoType,
                              }))
                            }
                            disabled={!checked}
                          >
                            <SelectTrigger className="h-6 flex-1 text-[10px]">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {PHOTO_TYPES.map((t) => (
                                <SelectItem key={t} value={t} className="text-xs">
                                  {t}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <a
                            href={c.url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-muted-foreground hover:text-foreground"
                            title="Abrir URL original"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
