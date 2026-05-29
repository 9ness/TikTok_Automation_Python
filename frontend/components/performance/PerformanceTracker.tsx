"use client";

import { useState } from "react";
import {
  BarChart3,
  Crown,
  ExternalLink,
  Eye,
  Heart,
  Loader2,
  Plus,
  RefreshCw,
  ShoppingBag,
  Trash2,
  TrendingUp,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useAddPublishedVideo,
  useDeletePublishedVideo,
  usePerformance,
  useRefreshPublishedVideo,
  useUpdatePublishedVideo,
  type AngleStat,
  type PublishedVideo,
} from "@/lib/queries/performance";
import type { Product } from "@/lib/types/product";

// Ángulos sugeridos (espejo de SUGGESTED_ANGLES del backend video_preset).
const SUGGESTED_ANGLES = [
  "dolor",
  "deseo",
  "prueba_social",
  "urgencia",
  "curiosidad",
  "comparativa",
  "identidad",
  "educativo",
];

/** Feedback loop: registra vídeos publicados + métricas reales para que el
 *  motor aprenda qué ángulos venden y los priorice al generar presets. */
export function PerformanceTracker({ product }: { product: Product }) {
  const perfQ = usePerformance(product.id);
  const data = perfQ.data;
  const videos = data?.items ?? [];
  const summary = data?.summary;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-emerald-500" />
        <h2 className="text-sm font-semibold sm:text-base">
          Rendimiento real ({videos.length})
        </h2>
        <span className="text-[10px] text-muted-foreground sm:text-xs">
          alimenta la generación de presets
        </span>
      </div>

      {summary && summary.total_videos > 0 && (
        <SummaryDashboard summary={summary} />
      )}

      <AddVideoForm product={product} />

      {perfQ.isLoading ? (
        <Card className="bg-muted/30">
          <CardContent className="p-4 text-center text-xs text-muted-foreground">
            Cargando…
          </CardContent>
        </Card>
      ) : videos.length === 0 ? (
        <Card className="bg-muted/30">
          <CardContent className="p-4 text-center text-xs text-muted-foreground sm:text-sm">
            Aún no has registrado vídeos publicados. Pega la URL de un TikTok
            que ya subiste con este producto + qué ángulo usaste. El motor
            aprenderá qué funciona y priorizará esos ángulos al generar.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {videos.map((v) => (
            <VideoRow key={v.id} video={v} productId={product.id} />
          ))}
        </div>
      )}
    </div>
  );
}

function SummaryDashboard({ summary }: { summary: NonNullable<ReturnType<typeof usePerformance>["data"]>["summary"] }) {
  const hasOrders = summary.total_orders > 0;
  return (
    <Card className="border-emerald-500/40 bg-emerald-500/5">
      <CardContent className="space-y-3 p-3 sm:p-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Vídeos" value={summary.total_videos.toLocaleString()} />
          <Stat label="Views" value={summary.total_views.toLocaleString()} />
          <Stat label="Pedidos" value={summary.total_orders.toLocaleString()} />
          <Stat
            label="Ingresos"
            value={`${summary.total_revenue_eur.toFixed(0)}€`}
          />
        </div>
        {summary.by_angle.length > 0 && (
          <div className="space-y-1">
            <p className="text-[10px] font-semibold uppercase text-muted-foreground sm:text-[11px]">
              Ranking por ángulo ({hasOrders ? "ventas" : "engagement"})
            </p>
            {summary.by_angle.slice(0, 5).map((a: AngleStat, i: number) => (
              <div
                key={a.angle}
                className="flex items-center gap-2 rounded border bg-card px-2 py-1 text-[11px] sm:text-xs"
              >
                {i === 0 ? (
                  <Crown className="h-3.5 w-3.5 flex-shrink-0 text-amber-500" />
                ) : (
                  <span className="w-3.5 flex-shrink-0 text-center text-muted-foreground">
                    {i + 1}
                  </span>
                )}
                <span className="min-w-0 flex-1 truncate font-medium">
                  {a.angle}
                </span>
                <span className="flex-shrink-0 text-muted-foreground">
                  {a.count} vid · {a.avg_views.toLocaleString()} views med
                  {hasOrders && ` · ${a.orders} ped`}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border bg-card p-2 text-center">
      <p className="text-sm font-bold sm:text-base">{value}</p>
      <p className="text-[9px] uppercase text-muted-foreground sm:text-[10px]">
        {label}
      </p>
    </div>
  );
}

function AddVideoForm({ product }: { product: Product }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [hook, setHook] = useState("");
  const [angle, setAngle] = useState("");
  const [orders, setOrders] = useState("");
  const [revenue, setRevenue] = useState("");
  const addMut = useAddPublishedVideo();

  // Ángulos sugeridos = SUGGESTED_ANGLES + los que ya usan sus presets.
  const presetAngles = Array.from(
    new Set((product.video_presets ?? []).map((p) => p.angle).filter(Boolean)),
  );
  const angleOptions = Array.from(
    new Set([...presetAngles, ...SUGGESTED_ANGLES]),
  );

  function reset() {
    setUrl("");
    setHook("");
    setAngle("");
    setOrders("");
    setRevenue("");
  }

  function onSubmit() {
    if (!url.trim().startsWith("http")) {
      toast.error("Pega una URL TikTok válida");
      return;
    }
    addMut.mutate(
      {
        productId: product.id,
        tiktok_url: url.trim(),
        hook_text: hook.trim(),
        angle: angle.trim(),
        orders: orders ? Number(orders) : 0,
        revenue_eur: revenue ? Number(revenue) : 0,
        refresh_now: true,
      },
      {
        onSuccess: () => {
          toast.success("Vídeo registrado · métricas actualizadas");
          reset();
          setOpen(false);
        },
        onError: (e) => toast.error(`Error: ${e.message}`),
      },
    );
  }

  if (!open) {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        className="h-9 w-full gap-1 border-dashed text-xs"
      >
        <Plus className="h-3.5 w-3.5" />
        Registrar vídeo publicado
      </Button>
    );
  }

  return (
    <Card className="border-emerald-500/40">
      <CardContent className="space-y-2.5 p-3 sm:p-4">
        <div className="space-y-1">
          <Label className="text-[11px]">URL del TikTok publicado</Label>
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.tiktok.com/@tu_cuenta/video/123…"
            className="h-9 text-xs"
            disabled={addMut.isPending}
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label className="text-[11px]">Ángulo usado</Label>
            <select
              value={angle}
              onChange={(e) => setAngle(e.target.value)}
              disabled={addMut.isPending}
              className="h-9 w-full rounded-md border bg-background px-2 text-xs"
            >
              <option value="">— elegir —</option>
              {angleOptions.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label className="text-[11px]">Pedidos</Label>
              <Input
                value={orders}
                onChange={(e) => setOrders(e.target.value.replace(/\D/g, ""))}
                placeholder="0"
                inputMode="numeric"
                className="h-9 text-xs"
                disabled={addMut.isPending}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-[11px]">€ ingresos</Label>
              <Input
                value={revenue}
                onChange={(e) =>
                  setRevenue(e.target.value.replace(/[^\d.]/g, ""))
                }
                placeholder="0"
                inputMode="decimal"
                className="h-9 text-xs"
                disabled={addMut.isPending}
              />
            </div>
          </div>
        </div>
        <div className="space-y-1">
          <Label className="text-[11px]">Hook usado (opcional)</Label>
          <Textarea
            value={hook}
            onChange={(e) => setHook(e.target.value)}
            placeholder="El hook on-screen que pusiste en este vídeo…"
            rows={2}
            className="text-xs"
            disabled={addMut.isPending}
          />
        </div>
        <div className="flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              reset();
              setOpen(false);
            }}
            disabled={addMut.isPending}
            className="h-8 text-xs"
          >
            Cancelar
          </Button>
          <Button
            size="sm"
            onClick={onSubmit}
            disabled={addMut.isPending}
            className="h-8 gap-1 bg-emerald-600 text-xs hover:bg-emerald-700"
          >
            {addMut.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Registrando…
              </>
            ) : (
              <>
                <Plus className="h-3.5 w-3.5" />
                Registrar
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function VideoRow({
  video,
  productId,
}: {
  video: PublishedVideo;
  productId: string;
}) {
  const [editing, setEditing] = useState(false);
  const [orders, setOrders] = useState(String(video.orders));
  const [revenue, setRevenue] = useState(String(video.revenue_eur));
  const refreshMut = useRefreshPublishedVideo();
  const updateMut = useUpdatePublishedVideo();
  const deleteMut = useDeletePublishedVideo();

  function saveEdit() {
    updateMut.mutate(
      {
        productId,
        videoId: video.id,
        orders: Number(orders) || 0,
        revenue_eur: Number(revenue) || 0,
      },
      {
        onSuccess: () => {
          toast.success("Actualizado");
          setEditing(false);
        },
        onError: (e) => toast.error(`Error: ${e.message}`),
      },
    );
  }

  return (
    <Card>
      <CardContent className="space-y-2 p-2.5 sm:p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              {video.angle && (
                <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-medium uppercase text-emerald-700 dark:text-emerald-300">
                  {video.angle}
                </span>
              )}
              <a
                href={video.tiktok_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 truncate text-[11px] text-cyan-600 hover:underline dark:text-cyan-400"
              >
                <span className="truncate">{video.tiktok_url}</span>
                <ExternalLink className="h-3 w-3 flex-shrink-0" />
              </a>
            </div>
            {video.hook_text && (
              <p className="mt-0.5 line-clamp-1 text-[11px] italic text-muted-foreground">
                “{video.hook_text}”
              </p>
            )}
          </div>
          <div className="flex flex-shrink-0 items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                refreshMut.mutate(
                  { productId, videoId: video.id },
                  {
                    onSuccess: () => toast.success("Métricas actualizadas"),
                    onError: (e) => toast.error(`Error: ${e.message}`),
                  },
                )
              }
              disabled={refreshMut.isPending}
              title="Refrescar métricas TikTok"
              className="h-7 w-7 p-0 text-muted-foreground hover:text-emerald-500"
            >
              {refreshMut.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                if (window.confirm("¿Borrar este vídeo del tracking?")) {
                  deleteMut.mutate({ productId, videoId: video.id });
                }
              }}
              disabled={deleteMut.isPending}
              title="Borrar"
              className="h-7 w-7 p-0 text-muted-foreground hover:text-red-500"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground sm:text-[11px]">
          <span className="flex items-center gap-1">
            <Eye className="h-3 w-3" />
            {video.views.toLocaleString()}
          </span>
          <span className="flex items-center gap-1">
            <Heart className="h-3 w-3" />
            {video.likes.toLocaleString()}
          </span>
          <span className="flex items-center gap-1">
            <TrendingUp className="h-3 w-3" />
            {video.views > 0
              ? (
                  ((video.likes + video.comments + video.shares) /
                    video.views) *
                  100
                ).toFixed(1)
              : "0"}
            %
          </span>
          {editing ? (
            <span className="flex items-center gap-1">
              <ShoppingBag className="h-3 w-3" />
              <input
                value={orders}
                onChange={(e) => setOrders(e.target.value.replace(/\D/g, ""))}
                className="h-6 w-12 rounded border bg-background px-1 text-[11px]"
                placeholder="ped"
              />
              <input
                value={revenue}
                onChange={(e) =>
                  setRevenue(e.target.value.replace(/[^\d.]/g, ""))
                }
                className="h-6 w-14 rounded border bg-background px-1 text-[11px]"
                placeholder="€"
              />
              <Button
                size="sm"
                onClick={saveEdit}
                disabled={updateMut.isPending}
                className="h-6 bg-emerald-600 px-2 text-[10px] hover:bg-emerald-700"
              >
                OK
              </Button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="flex items-center gap-1 rounded px-1 hover:bg-muted"
              title="Editar pedidos/ingresos"
            >
              <ShoppingBag className="h-3 w-3" />
              {video.orders} ped · {video.revenue_eur.toFixed(0)}€
            </button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
