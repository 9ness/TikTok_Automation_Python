"use client";

import { useState } from "react";
import { AlertCircle } from "lucide-react";

import { HistoryFilters, type HistoryFiltersValue } from "@/components/history/HistoryFilters";
import { HistoryTable } from "@/components/history/HistoryTable";
import { VideoPlayer } from "@/components/history/VideoPlayer";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useGenerations } from "@/lib/queries/generations";
import type { GenerationResponse } from "@/lib/types/generation";

const DEFAULT_FILTERS: HistoryFiltersValue = {
  username: "",
  productId: "",
  status: "__all__",
};

export default function ShopHistoryPage() {
  const [filters, setFilters] = useState<HistoryFiltersValue>(DEFAULT_FILTERS);
  const [selected, setSelected] = useState<GenerationResponse | null>(null);

  const queryFilters = {
    limit: 100,
    username: filters.username.trim() || undefined,
    product_id: filters.productId.trim() || undefined,
    status: filters.status === "__all__" ? undefined : filters.status,
  };
  const generations = useGenerations(queryFilters);

  return (
    <div className="container mx-auto p-6 md:p-10">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Histórico</h1>
        <p className="text-sm text-muted-foreground">
          Vídeos generados. Click en una fila para reproducir.
        </p>
      </div>

      <div className="mb-4">
        <HistoryFilters
          value={filters}
          onChange={setFilters}
          onReset={() => setFilters(DEFAULT_FILTERS)}
        />
      </div>

      {generations.isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {generations.isError && (
        <Card>
          <CardContent className="flex items-center gap-3 p-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <div>
              <p className="font-medium">Error cargando histórico</p>
              <p className="text-sm text-muted-foreground">
                {generations.error?.message ?? "Sin detalles"}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {generations.data && (
        <>
          <p className="mb-2 text-xs text-muted-foreground">
            {generations.data.total} generaciones
          </p>
          <HistoryTable items={generations.data.items} onRowClick={setSelected} />
        </>
      )}

      <VideoPlayer
        generation={selected}
        open={selected !== null}
        onOpenChange={(next) => !next && setSelected(null)}
      />
    </div>
  );
}
