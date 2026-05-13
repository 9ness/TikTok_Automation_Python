"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

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
import { useJobsWithCosts, type JobCost } from "@/lib/queries/costs";

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const PROGRAMS = [
  { value: "all", label: "Todos" },
  { value: "creator_reward", label: "Creator Reward" },
  { value: "tiktok_shop", label: "TikTok Shop" },
];

const MODES_BY_PROGRAM: Record<string, { value: string; label: string }[]> = {
  all: [],
  creator_reward: [
    { value: "presidents", label: "Presidentes Top 5" },
    { value: "pronosticos", label: "Pronósticos Diarios" },
    { value: "copyright", label: "Quitar Copy" },
    { value: "subs_auto", label: "Subs sobre Vídeo" },
  ],
  tiktok_shop: [{ value: "tiktok_shop", label: "TikTok Shop" }],
};

export default function CostsPage() {
  const [month, setMonth] = useState<string>(currentMonth());
  const [program, setProgram] = useState<string>("all");
  const [mode, setMode] = useState<string>("all");
  const [user, setUser] = useState<string>("");
  const [productId, setProductId] = useState<string>("");

  const q = useJobsWithCosts({
    month,
    program: program === "all" ? undefined : program,
    mode: mode === "all" ? undefined : mode,
    user: user.trim() || undefined,
    product_id: productId.trim() || undefined,
  });

  const data = q.data;

  return (
    <div className="container mx-auto space-y-4 p-6 md:p-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Costes</h1>
        <p className="text-sm text-muted-foreground">
          Gasto por job de cualquier modo (Creator Reward + TikTok Shop).
        </p>
      </header>

      {/* Filtros */}
      <Card>
        <CardContent className="grid gap-3 p-3 md:grid-cols-5">
          <div className="space-y-1">
            <Label className="text-xs">Mes</Label>
            <Input
              type="month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              className="h-9"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Programa</Label>
            <Select value={program} onValueChange={(v) => { setProgram(v); setMode("all"); }}>
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PROGRAMS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Modo</Label>
            <Select value={mode} onValueChange={setMode} disabled={program === "all"}>
              <SelectTrigger className="h-9"><SelectValue placeholder="Todos" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {(MODES_BY_PROGRAM[program] ?? []).map((m) => (
                  <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Usuario</Label>
            <Input
              value={user}
              onChange={(e) => setUser(e.target.value)}
              placeholder="ness / buga / @user"
              className="h-9"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Producto (TT Shop)</Label>
            <Input
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              placeholder="product_id"
              className="h-9"
            />
          </div>
        </CardContent>
      </Card>

      {/* Summary */}
      {q.isLoading && (
        <Card><CardContent className="flex items-center gap-2 p-3 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
        </CardContent></Card>
      )}
      {data && (
        <>
          <div className="grid gap-3 md:grid-cols-4">
            <KpiCard label="Total" value={`$${data.summary.total_usd.toFixed(3)}`} />
            <KpiCard label="Jobs" value={String(data.summary.count)} />
            <KpiCard
              label="Coste medio / job"
              value={
                data.summary.count > 0
                  ? `$${(data.summary.total_usd / data.summary.count).toFixed(3)}`
                  : "—"
              }
            />
            <KpiCard label="Mes" value={data.month} />
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <BreakdownCard title="Por programa" data={data.summary.by_program} />
            <BreakdownCard title="Por modo" data={data.summary.by_mode} />
            <BreakdownCard title="Por API (kind)" data={data.summary.by_kind} />
          </div>

          <BreakdownCard
            title="Por usuario"
            data={data.summary.by_user}
            className="!grid-cols-1"
          />

          {/* Tabla de jobs */}
          <Card>
            <CardContent className="p-0">
              <div className="border-b px-4 py-2 text-sm font-semibold">
                Jobs ({data.jobs.length})
              </div>
              <div className="max-h-[60vh] overflow-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-card">
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="px-3 py-2">job_id</th>
                      <th className="px-3 py-2">programa</th>
                      <th className="px-3 py-2">modo</th>
                      <th className="px-3 py-2">user</th>
                      <th className="px-3 py-2">título</th>
                      <th className="px-3 py-2 text-right">$ total</th>
                      <th className="px-3 py-2">desglose</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.jobs.map((j) => (
                      <JobRow key={j.job_id} j={j} />
                    ))}
                    {data.jobs.length === 0 && (
                      <tr><td colSpan={7} className="p-4 text-center text-muted-foreground">
                        Sin jobs en ese filtro.
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <Card><CardContent className="space-y-1 p-3">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="text-2xl font-bold tabular-nums">{value}</p>
    </CardContent></Card>
  );
}

function BreakdownCard({
  title,
  data,
  className,
}: {
  title: string;
  data: Record<string, number>;
  className?: string;
}) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((acc, [, v]) => acc + v, 0);
  return (
    <Card><CardContent className={`space-y-2 p-3 ${className ?? ""}`}>
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </p>
      {entries.length === 0 && (
        <p className="text-xs text-muted-foreground">(vacío)</p>
      )}
      <div className="space-y-1.5">
        {entries.map(([k, v]) => {
          const pct = total > 0 ? (v / total) * 100 : 0;
          return (
            <div key={k} className="space-y-0.5">
              <div className="flex items-center justify-between text-xs">
                <span className="truncate">{k}</span>
                <span className="font-mono">${v.toFixed(3)}</span>
              </div>
              <div className="h-1 w-full overflow-hidden rounded-full bg-secondary">
                <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </CardContent></Card>
  );
}

function JobRow({ j }: { j: JobCost }) {
  const [open, setOpen] = useState(false);
  const date = new Date(j.started_at * 1000).toLocaleString("es-ES", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
  return (
    <>
      <tr className="border-b cursor-pointer hover:bg-accent/30" onClick={() => setOpen(!open)}>
        <td className="px-3 py-2 font-mono">{j.job_id.slice(0, 8)}</td>
        <td className="px-3 py-2">{j.program}</td>
        <td className="px-3 py-2">{j.mode}</td>
        <td className="px-3 py-2">{j.user ?? "—"}</td>
        <td className="px-3 py-2 max-w-xs truncate" title={j.title ?? ""}>
          <span className="text-muted-foreground">{date} · </span>
          {j.title ?? "—"}
        </td>
        <td className="px-3 py-2 text-right font-mono font-semibold">
          ${j.total_usd.toFixed(4)}
        </td>
        <td className="px-3 py-2 text-muted-foreground">
          {j.lines.length} línea{j.lines.length === 1 ? "" : "s"}
        </td>
      </tr>
      {open && (
        <tr className="border-b bg-muted/20">
          <td colSpan={7} className="px-4 py-2">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-left text-muted-foreground">
                  <th className="py-1">kind</th>
                  <th className="py-1">units</th>
                  <th className="py-1">detail</th>
                  <th className="py-1 text-right">$ cost</th>
                </tr>
              </thead>
              <tbody>
                {j.lines.map((l, i) => (
                  <tr key={i}>
                    <td className="py-0.5 font-mono">{l.kind}</td>
                    <td className="py-0.5">{l.units.toLocaleString()} {l.unit_label}</td>
                    <td className="py-0.5 text-muted-foreground">{l.detail ?? "—"}</td>
                    <td className="py-0.5 text-right font-mono">${l.cost_usd.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}
