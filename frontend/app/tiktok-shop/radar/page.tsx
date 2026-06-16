"use client";

import { useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ExternalLink,
  Loader2,
  Package,
  Radar as RadarIcon,
  Rocket,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  useRadarCandidates,
  useRadarClear,
  useRadarImport,
  useRadarRegions,
  useRadarScan,
  type RadarCandidate,
} from "@/lib/queries/radar";
import { cn } from "@/lib/utils";

const SORTS = [
  { value: "commission", label: "💰 Mejor comisión" },
  { value: "score", label: "⭐ Score ganador" },
  { value: "gmv", label: "💶 Más facturación" },
  { value: "gmv_max", label: "🚀 GMV Max" },
  { value: "growth", label: "📈 Crecimiento" },
  { value: "creators", label: "👥 Menos creadores" },
];

const FLAGS: Record<string, string> = {
  ES: "🇪🇸", DE: "🇩🇪", FR: "🇫🇷", IT: "🇮🇹", GB: "🇬🇧", US: "🇺🇸", BR: "🇧🇷", MX: "🇲🇽",
};

export default function RadarPage() {
  const qc = useQueryClient();
  const regionsQ = useRadarRegions();
  const scan = useRadarScan();
  const clear = useRadarClear();

  const [regions, setRegions] = useState<string[]>(["ES"]);
  const [keywords, setKeywords] = useState("crocs\nventilador techo\ncreatina\nbotella termo\nhumidificador");
  const [maxInfluencers, setMaxInfluencers] = useState(200);
  const [minCommission, setMinCommission] = useState(0);
  const [minUnits, setMinUnits] = useState(5);
  const [minScore, setMinScore] = useState(25);
  const [requireAds, setRequireAds] = useState(false);
  const [deepAds, setDeepAds] = useState(true);
  const [sort, setSort] = useState("commission");

  const candidatesQ = useRadarCandidates(sort);
  const items = candidatesQ.data ?? [];

  const toggleRegion = (code: string) =>
    setRegions((r) => (r.includes(code) ? r.filter((x) => x !== code) : [...r, code]));

  const runScan = () => {
    const kws = keywords.split("\n").map((k) => k.trim()).filter(Boolean);
    if (regions.length === 0) return toast.error("Elige al menos un país.");
    scan.mutate(
      {
        regions,
        keywords: kws,
        deep_ads: deepAds,
        max_influencers: maxInfluencers,
        min_commission_pct: minCommission,
        min_units_sold: minUnits,
        min_score: minScore,
        require_ads_signal: requireAds,
      },
      {
        onSuccess: (res) => {
          if (!res.configured) return toast.error(res.hint || "EchoTik no configurado.");
          if (res.quota_exhausted) toast.error("🚫 EchoTik sin cuota (trial agotado).");
          toast.success(`${res.found} ganadores en ${res.scanned_regions.join(", ")}`);
          qc.invalidateQueries({ queryKey: ["radar-candidates"] });
        },
        onError: (e) => toast.error(`Error: ${e.message}`),
      },
    );
  };

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex items-center gap-2">
        <RadarIcon className="h-6 w-6 text-orange-500" />
        <h1 className="text-xl font-bold sm:text-2xl">Radar de Productos</h1>
      </div>
      <p className="text-xs text-muted-foreground sm:text-sm">
        Descubre productos con <b>inyección de ADS (GMV Max)</b> y <b>pocos creadores</b>.
        Ordena por comisión y prueba los mejores — da igual el país, vendes desde España.
      </p>

      {/* Configuración del scan */}
      <Card>
        <CardContent className="space-y-3 p-4">
          {/* Países */}
          <div>
            <label className="text-xs font-medium">Países (EchoTik)</label>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {(regionsQ.data?.regions ?? [{ code: "ES", label: "🇪🇸 España" }]).map((r) => (
                <button
                  key={r.code}
                  onClick={() => toggleRegion(r.code)}
                  className={cn(
                    "rounded-full border px-2.5 py-1 text-xs transition",
                    regions.includes(r.code)
                      ? "border-orange-500 bg-orange-500/10 font-medium"
                      : "border-border text-muted-foreground hover:border-foreground/40",
                  )}
                >
                  {r.label}
                </button>
              ))}
            </div>
            {regionsQ.data?.unsupported_eu && (
              <p className="mt-1 text-[10px] text-muted-foreground">
                EU sin datos en EchoTik: {regionsQ.data.unsupported_eu.join(", ")}
              </p>
            )}
          </div>

          {/* Keywords */}
          <div>
            <label className="text-xs font-medium">Nichos / keywords (una por línea)</label>
            <textarea
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              rows={4}
              className="mt-1 w-full rounded-md border border-border bg-background p-2 text-xs"
            />
          </div>

          {/* Filtros */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label="Máx creadores">
              <Input type="number" value={maxInfluencers} onChange={(e) => setMaxInfluencers(+e.target.value)} />
            </Field>
            <Field label="Comisión mín %">
              <Input type="number" value={minCommission} onChange={(e) => setMinCommission(+e.target.value)} />
            </Field>
            <Field label="Uds vendidas mín">
              <Input type="number" value={minUnits} onChange={(e) => setMinUnits(+e.target.value)} />
            </Field>
            <Field label="Score mín">
              <Input type="number" value={minScore} onChange={(e) => setMinScore(+e.target.value)} />
            </Field>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <Toggle checked={deepAds} onChange={setDeepAds} label="📢 Deducir GMV Max (vídeos)" />
            <Toggle checked={requireAds} onChange={setRequireAds} label="Exigir señal de ADS" />
          </div>

          <Button onClick={runScan} disabled={scan.isPending} className="w-full sm:w-auto">
            {scan.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
            Escanear ahora
          </Button>
          {scan.isPending && (
            <p className="text-xs text-muted-foreground">
              Escaneando {regions.length} país(es)… puede tardar unos segundos.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Resultados */}
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">
          {items.length} candidatos · {items.filter((c) => c.imported).length} importados
        </p>
        <div className="flex items-center gap-2">
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="rounded-md border border-border bg-background px-2 py-1 text-xs"
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              clear.mutate(undefined, {
                onSuccess: (r) => {
                  toast.success(`${r.deleted} eliminados`);
                  qc.invalidateQueries({ queryKey: ["radar-candidates"] });
                },
              })
            }
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {candidatesQ.isLoading ? (
        <p className="text-sm text-muted-foreground">Cargando candidatos…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Sin candidatos. Pulsa <b>Escanear ahora</b> arriba.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((c) => (
            <RadarCard key={c.product_id} c={c} onImported={() => qc.invalidateQueries({ queryKey: ["radar-candidates"] })} />
          ))}
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="text-[10px] text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex cursor-pointer items-center gap-1.5 text-xs">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function RadarCard({ c, onImported }: { c: RadarCandidate; onImported: () => void }) {
  const imp = useRadarImport();
  const boosted = c.ads.probable_boosted;
  const verdictColor =
    c.ads.verdict === "fuerte" ? "text-red-500" : c.ads.verdict === "media" ? "text-orange-500" : "text-muted-foreground";

  return (
    <Card className="overflow-hidden">
      <CardContent className="space-y-2 p-3">
        <div className="flex gap-2">
          {c.cover_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={c.cover_url} alt="" className="h-16 w-16 shrink-0 rounded object-cover" />
          ) : (
            <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded bg-muted">
              <Package className="h-5 w-5 text-muted-foreground" />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <p className="line-clamp-2 text-xs font-medium">
              {FLAGS[c.region] ?? ""} {c.name}
            </p>
            <p className="mt-0.5 text-sm font-bold text-green-600">
              💰 {c.commission_pct.toFixed(0)}% comisión
            </p>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-lg font-bold">{c.score.total.toFixed(0)}</div>
            <div className="text-[10px] text-muted-foreground">score</div>
          </div>
        </div>

        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
          <span><Users className="mr-0.5 inline h-3 w-3" />{c.influencer_count} creadores</span>
          <span>💶 €{(c.gmv_30d || c.gmv).toLocaleString("es-ES", { maximumFractionDigits: 0 })}</span>
          <span>{c.units_sold} uds</span>
          {c.growth_pct !== null && <span>📈 {c.growth_pct > 0 ? "+" : ""}{c.growth_pct.toFixed(0)}%</span>}
        </div>

        <div className={cn("text-xs font-medium", boosted ? "text-red-500" : verdictColor)}>
          {boosted ? "🚀 GMV Max probable" : `📢 GMV Max ${c.ads.verdict}`} ({c.ads.gmv_max_likelihood.toFixed(0)}/100)
          {c.ads.ad_labels_available && c.ads.ad_labeled_videos > 0 && ` · 🏷️ ${c.ads.ad_labeled_videos} AD`}
        </div>
        {c.ads.reasons.length > 0 && (
          <p className="line-clamp-2 text-[10px] text-muted-foreground">{c.ads.reasons.join(" · ")}</p>
        )}

        <div className="flex items-center gap-2 pt-1">
          {c.imported ? (
            <span className="flex items-center gap-1 text-xs text-green-600">
              <Check className="h-3 w-3" /> Importado
            </span>
          ) : (
            <Button
              size="sm"
              disabled={imp.isPending}
              onClick={() =>
                imp.mutate(
                  { product_id: c.product_id },
                  {
                    onSuccess: (r) => {
                      if (r.ok) { toast.success(r.message); onImported(); }
                      else toast.error(r.message);
                    },
                    onError: (e) => toast.error(e.message),
                  },
                )
              }
            >
              {imp.isPending ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Rocket className="mr-1 h-3 w-3" />}
              Importar
            </Button>
          )}
          {c.tiktok_url && (
            <a href={c.tiktok_url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground">
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
