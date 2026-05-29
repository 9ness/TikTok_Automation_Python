"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Check,
  ExternalLink,
  Loader2,
  Package,
  Plus,
  Search,
  TrendingUp,
  Users,
  Video,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  useDiscoverProducts,
  type DiscoveredProduct,
} from "@/lib/queries/discovery";
import { useCreateProduct } from "@/lib/queries/products";
import { cn } from "@/lib/utils";

const SORTS = [
  { value: "sales", label: "Más vendidos (total)" },
  { value: "sales_30d", label: "Ventas último mes" },
  { value: "sales_7d", label: "Ventas última semana" },
  { value: "gmv", label: "Más facturación (€)" },
  { value: "commission", label: "Mejor comisión (%)" },
  { value: "price_desc", label: "Precio ↓" },
  { value: "price_asc", label: "Precio ↑" },
];

// Nichos rápidos — rellenan la keyword en 1 toque (no hay taxonomía de
// categorías en la API, así que usamos búsquedas por nicho en español).
const NICHES = [
  "Belleza", "Maquillaje", "Cuidado facial", "Fitness", "Hogar",
  "Cocina", "Mascotas", "Tecnología", "Moda", "Salud", "Bebé", "Coche",
];

const MIN_COMMISSIONS = [
  { value: 0, label: "Comisión: cualquiera" },
  { value: 5, label: "Comisión ≥ 5%" },
  { value: 10, label: "Comisión ≥ 10%" },
  { value: 15, label: "Comisión ≥ 15%" },
  { value: 20, label: "Comisión ≥ 20%" },
];

export default function DiscoverPage() {
  const [keyword, setKeyword] = useState("");
  // Orden + comisión son filtros LOCALES — cambiarlos NO re-llama a la API.
  const [sort, setSort] = useState("sales");
  const [minCommission, setMinCommission] = useState(0);
  // `submitted` (keyword) solo cambia al pulsar Buscar → 1 request por búsqueda.
  const [submitted, setSubmitted] = useState<string | null>(null);

  // La búsqueda SOLO depende de la keyword → 1 llamada por búsqueda.
  const q = useDiscoverProducts({
    keyword: submitted ?? "",
    limit: 10,
    enabled: Boolean(submitted),
  });

  function runSearch(kw: string) {
    if (!kw.trim()) {
      toast.error("Escribe qué producto o nicho buscar (ej. 'cinta de correr')");
      return;
    }
    setSubmitted(kw.trim());
  }
  function onSearch() {
    runSearch(keyword);
  }
  function onNiche(niche: string) {
    setKeyword(niche);
    runSearch(niche);
  }

  const data = q.data;
  // Orden + filtro de comisión aplicados en el cliente sobre el resultado
  // ya cargado → instantáneo y SIN gastar llamadas.
  const items = useMemo(() => {
    const list = [...(data?.items ?? [])];
    const filtered =
      minCommission > 0
        ? list.filter((p) => (p.commission_pct ?? 0) >= minCommission)
        : list;
    const key: Record<string, keyof typeof filtered[number]> = {
      sales: "units_sold",
      sales_30d: "units_sold_30d",
      sales_7d: "units_sold_7d",
      gmv: "gmv",
      commission: "commission_pct",
      price_desc: "max_price",
      price_asc: "min_price",
    };
    const k = key[sort] ?? "units_sold";
    filtered.sort((a, b) => {
      const av = (a[k] as number) || 0;
      const bv = (b[k] as number) || 0;
      return sort === "price_asc" ? av - bv : bv - av;
    });
    return filtered;
  }, [data?.items, sort, minCommission]);

  return (
    <div className="container mx-auto space-y-4 p-3 sm:p-6 md:p-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Buscar Productos</h1>
        <p className="text-sm text-muted-foreground">
          Descubre qué se vende de verdad en TikTok Shop España y añádelo a tus
          productos en 1 clic.
        </p>
      </header>

      {/* Barra de búsqueda — mobile-first */}
      <Card>
        <CardContent className="space-y-2 p-3 sm:p-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onSearch()}
              placeholder="ej. cinta de correr, perfume, organizador cocina…"
              className="h-10 flex-1 text-sm"
            />
            <Button
              onClick={onSearch}
              disabled={q.isFetching}
              className="h-10 gap-1 px-4"
            >
              {q.isFetching ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              Buscar
            </Button>
          </div>

          {/* Filtros: orden + comisión mínima */}
          <div className="flex flex-col gap-2 sm:flex-row">
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="h-9 flex-1 rounded-md border bg-background px-2 text-xs"
            >
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  Ordenar: {s.label}
                </option>
              ))}
            </select>
            <select
              value={minCommission}
              onChange={(e) => setMinCommission(Number(e.target.value))}
              className="h-9 flex-1 rounded-md border bg-background px-2 text-xs"
            >
              {MIN_COMMISSIONS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          {/* Chips de nicho — búsqueda en 1 toque */}
          <div className="flex flex-wrap gap-1.5">
            {NICHES.map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => onNiche(n)}
                className="rounded-full border bg-muted/40 px-2.5 py-1 text-[10px] font-medium transition-colors hover:border-emerald-500/60 hover:bg-emerald-500/10 sm:text-[11px]"
              >
                {n}
              </button>
            ))}
          </div>

          <p className="text-[10px] text-muted-foreground sm:text-[11px]">
            🇪🇸 Datos reales de ventas en España. Cada <b>búsqueda</b> gasta 1
            consulta; ordenar y filtrar por comisión después es <b>gratis</b>.
          </p>
        </CardContent>
      </Card>

      {/* Estados */}
      {q.isError && (
        <Card className="border-red-500/40 bg-red-500/5">
          <CardContent className="p-4 text-sm text-red-600 dark:text-red-400">
            Error al buscar: {(q.error as Error)?.message}
          </CardContent>
        </Card>
      )}

      {data && !data.configured && (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardContent className="p-4 text-sm text-amber-700 dark:text-amber-300">
            {data.hint}
          </CardContent>
        </Card>
      )}

      {data && data.configured && data.hint && items.length > 0 && (
        <p className="rounded bg-muted/40 px-3 py-1.5 text-[11px] text-muted-foreground">
          {data.hint}
        </p>
      )}

      {data && data.configured && items.length === 0 && !data.hint && (
        <Card className="bg-muted/30">
          <CardContent className="p-6 text-center text-sm text-muted-foreground">
            Sin resultados. Prueba otra palabra clave.
          </CardContent>
        </Card>
      )}

      {!submitted && (
        <Card className="bg-muted/30">
          <CardContent className="p-6 text-center text-sm text-muted-foreground">
            Escribe un producto o nicho y pulsa Buscar para ver qué vende en ES.
          </CardContent>
        </Card>
      )}

      {/* Grid de resultados — 2 cols móvil / 3 sm / 4 lg */}
      {items.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 lg:grid-cols-4">
          {items.map((p) => (
            <DiscoverCard key={p.product_id} product={p} />
          ))}
        </div>
      )}
    </div>
  );
}

function DiscoverCard({ product: p }: { product: DiscoveredProduct }) {
  const createMut = useCreateProduct();
  const [added, setAdded] = useState(false);
  // Las covers de EchoTik (CDN echosell) suelen dar 403 desde fuera →
  // si la imagen falla, mostramos el icono en vez de imagen rota.
  const [imgError, setImgError] = useState(false);
  const showImg = Boolean(p.cover_url) && !imgError;

  function onAdd() {
    createMut.mutate(
      {
        name: p.name,
        category: "otros",
        language: "es_ES",
        tiktok_shop: {
          product_url: p.tiktok_url,
          price_eur: p.min_price || null,
        },
        image_url_to_download: p.cover_url || null,
        analyze_with_gemini: false,
      },
      {
        onSuccess: () => {
          setAdded(true);
          toast.success("Añadido a Mis productos · ahora sube fotos y analiza");
        },
        onError: (e) => toast.error(`Error: ${e.message}`),
      },
    );
  }

  const priceLabel =
    p.min_price && p.max_price && p.min_price !== p.max_price
      ? `${p.min_price.toFixed(0)}-${p.max_price.toFixed(0)}€`
      : `${(p.min_price || p.max_price || 0).toFixed(0)}€`;

  // Comisión en € = precio medio × % comisión (idea aproximada por venta).
  const basePrice =
    p.min_price && p.max_price
      ? (p.min_price + p.max_price) / 2
      : p.min_price || p.max_price || 0;
  const commEur = (basePrice * (p.commission_pct || 0)) / 100;
  const commLabel =
    p.commission_pct > 0
      ? `${p.commission_pct}%${commEur > 0 ? ` (${commEur.toFixed(2)}€)` : ""}`
      : "";

  return (
    <Card className="flex flex-col overflow-hidden">
      <div className="relative aspect-square w-full bg-muted/30">
        {showImg ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={p.cover_url}
            alt={p.name}
            className="h-full w-full object-cover"
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-muted-foreground">
            <Package className="h-7 w-7" />
            <span className="text-[8px] uppercase tracking-wide">producto</span>
          </div>
        )}
        {p.units_sold > 0 && (
          <span className="absolute left-1 top-1 rounded bg-emerald-600/90 px-1.5 py-0.5 text-[10px] font-semibold text-white">
            {p.units_sold.toLocaleString()} vendidos
          </span>
        )}
        <a
          href={p.tiktok_url}
          target="_blank"
          rel="noopener noreferrer"
          className="absolute right-1 top-1 rounded bg-black/50 p-1 text-white hover:bg-black/70"
          title="Ver en TikTok Shop"
        >
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>

      <CardContent className="flex flex-1 flex-col gap-1.5 p-2">
        <p
          className="line-clamp-2 text-[11px] font-medium leading-tight sm:text-xs"
          title={p.name}
        >
          {p.name}
        </p>

        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] text-muted-foreground sm:text-[10px]">
          <span className="font-semibold text-foreground">{priceLabel}</span>
          {commLabel && (
            <span className="rounded bg-amber-500/15 px-1 font-semibold text-amber-700 dark:text-amber-300">
              {commLabel} com.
            </span>
          )}
          {p.gmv > 0 && (
            <span className="inline-flex items-center gap-0.5">
              <TrendingUp className="h-2.5 w-2.5" />
              {p.gmv >= 1000
                ? `${(p.gmv / 1000).toFixed(1)}k€`
                : `${p.gmv.toFixed(0)}€`}
            </span>
          )}
          {p.video_count > 0 && (
            <span className="inline-flex items-center gap-0.5">
              <Video className="h-2.5 w-2.5" />
              {p.video_count}
            </span>
          )}
          {p.influencer_count > 0 && (
            <span className="inline-flex items-center gap-0.5">
              <Users className="h-2.5 w-2.5" />
              {p.influencer_count}
            </span>
          )}
        </div>

        {p.tiktok_url && (
          <a
            href={p.tiktok_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-0.5 text-[9px] text-cyan-600 hover:underline dark:text-cyan-400 sm:text-[10px]"
          >
            <ExternalLink className="h-2.5 w-2.5" />
            Ver en TikTok Shop
          </a>
        )}

        <Button
          size="sm"
          onClick={onAdd}
          disabled={createMut.isPending || added}
          className={cn(
            "mt-auto h-7 gap-1 text-[10px]",
            added && "bg-emerald-600 hover:bg-emerald-600",
          )}
        >
          {createMut.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : added ? (
            <Check className="h-3 w-3" />
          ) : (
            <Plus className="h-3 w-3" />
          )}
          {added ? "Añadido" : "Añadir"}
        </Button>
        {added && (
          <Link
            href="/tiktok-shop/products"
            className="text-center text-[9px] text-cyan-600 hover:underline dark:text-cyan-400"
          >
            Ir a Mis productos →
          </Link>
        )}
      </CardContent>
    </Card>
  );
}
