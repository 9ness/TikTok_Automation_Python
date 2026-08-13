"use client";

import { useMemo, useState } from "react";
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
import { useEditorUsers } from "@/lib/queries/editor-auto";
import { useProducts } from "@/lib/queries/products";
import { useUser, useUsers } from "@/lib/queries/users";

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

type Program = "all" | "creator_reward" | "tiktok_shop" | "editor_auto" | "web";

const PROGRAMS: { value: Program; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "creator_reward", label: "Creator Reward" },
  { value: "tiktok_shop", label: "TikTok Shop" },
  { value: "editor_auto", label: "Editor Auto" },
  // Lo que se lanza desde la web y no pasa por la cola: obtener textos,
  // escribir guiones, emparejar los vídeos de una tanda, mirar la mano. Se
  // agrupa en un "trabajo" por día.
  { value: "web", label: "Desde la web" },
];

const MODES_BY_PROGRAM: Record<Program, { value: string; label: string }[]> = {
  all: [],
  creator_reward: [
    { value: "presidents", label: "Presidentes Top 5" },
    { value: "pronosticos", label: "Pronósticos Diarios" },
    { value: "copyright", label: "Quitar Copy" },
    { value: "subs_auto", label: "Subs sobre Vídeo" },
    { value: "construccion_pov", label: "Construcción POV" },
  ],
  tiktok_shop: [{ value: "tiktok_shop", label: "TikTok Shop" }],
  editor_auto: [{ value: "editor_auto", label: "Editor Auto" }],
  web: [{ value: "web", label: "Desde la web" }],
};

// Operadores Creator Reward (los que pueden encolar jobs). Si en el futuro
// el `/auth/me` devuelve `available_users`, podríamos cargarlos de ahí.
const CR_OPERATORS = ["ness", "buga"];

export default function CostsPage() {
  const [month, setMonth] = useState<string>(currentMonth());
  const [program, setProgram] = useState<Program>("all");
  const [mode, setMode] = useState<string>("all");
  // Para creator_reward: operador (ness/buga). Para tiktok_shop: username TT Shop.
  // Para editor_auto: nombre del EditorUser que ejecutó el flujo.
  const [crOperator, setCrOperator] = useState<string>("all");
  const [shopUser, setShopUser] = useState<string>("all");
  const [editorUser, setEditorUser] = useState<string>("all");
  const [productId, setProductId] = useState<string>("all");

  // Datos para los dropdowns
  const shopUsers = useUsers({ limit: 100 });
  const selectedUser = useUser(shopUser !== "all" ? shopUser : undefined);
  const allProducts = useProducts({ limit: 200 });
  const editorUsers = useEditorUsers();

  // Productos del user seleccionado (cascada). Si "all" → todos.
  const productsForUser = useMemo(() => {
    const all = allProducts.data?.items ?? [];
    if (shopUser === "all") return all;
    const assigned = new Set(selectedUser.data?.assigned_products ?? []);
    return all.filter((p) => assigned.has(p.id));
  }, [allProducts.data, selectedUser.data, shopUser]);

  // Reset de filtros dependientes cuando cambia el programa.
  function handleProgramChange(p: Program) {
    setProgram(p);
    setMode("all");
    setCrOperator("all");
    setShopUser("all");
    setEditorUser("all");
    setProductId("all");
  }

  // Calcular `user` y `product_id` que se mandan al backend según el programa.
  // Backend filtra por `cost:by_user:{user}` SET: para editor_auto el user
  // es el EditorUser.name (lo rellena `dispatch_job` desde params.user_name).
  const filterUser =
    program === "tiktok_shop"
      ? shopUser !== "all"
        ? shopUser
        : undefined
      : program === "creator_reward"
        ? crOperator !== "all"
          ? crOperator
          : undefined
        : program === "editor_auto"
          ? editorUser !== "all"
            ? editorUser
            : undefined
          : undefined;
  const filterProductId =
    program === "tiktok_shop" && productId !== "all" ? productId : undefined;

  const q = useJobsWithCosts({
    month,
    program: program === "all" ? undefined : program,
    mode: mode === "all" ? undefined : mode,
    user: filterUser,
    product_id: filterProductId,
  });

  const data = q.data;

  return (
    <div className="container mx-auto space-y-4 p-6 md:p-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Costes</h1>
        <p className="text-sm text-muted-foreground">
          Gasto por job de cualquier modo (Creator Reward + TikTok Shop + Editor Auto).
        </p>
      </header>

      {/* Filtros — adaptables al programa seleccionado */}
      <Card>
        <CardContent className="grid gap-3 p-3 md:grid-cols-5">
          <FilterField label="Mes">
            <Input
              type="month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              className="h-9"
            />
          </FilterField>

          <FilterField label="Programa">
            <Select value={program} onValueChange={(v) => handleProgramChange(v as Program)}>
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PROGRAMS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>

          <FilterField label="Modo">
            <Select value={mode} onValueChange={setMode} disabled={program === "all"}>
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Todos" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {(MODES_BY_PROGRAM[program] ?? []).map((m) => (
                  <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>

          {/* Usuario — UI distinta según programa */}
          {program === "tiktok_shop" ? (
            <FilterField label="Usuario (TT Shop)">
              <Select
                value={shopUser}
                onValueChange={(v) => {
                  setShopUser(v);
                  setProductId("all");
                }}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  {(shopUsers.data?.items ?? []).map((u) => {
                    // username puede venir con o sin '@'. Normalizamos para
                    // que el display sea siempre `@xxx` (un solo @) y el
                    // valor enviado al backend sea el username raw.
                    const label = u.username.startsWith("@")
                      ? u.username
                      : `@${u.username}`;
                    return (
                      <SelectItem key={u.username} value={u.username}>
                        {label}
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </FilterField>
          ) : program === "creator_reward" ? (
            <FilterField label="Operador">
              <Select value={crOperator} onValueChange={setCrOperator}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  {CR_OPERATORS.map((u) => (
                    <SelectItem key={u} value={u}>{u}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FilterField>
          ) : program === "editor_auto" ? (
            <FilterField label="Usuario (Editor)">
              <Select value={editorUser} onValueChange={setEditorUser}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  {(editorUsers.data ?? []).map((u) => (
                    <SelectItem key={u.id} value={u.name}>
                      {u.display_name || u.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FilterField>
          ) : (
            <FilterField label="Usuario">
              <Select disabled value="all" onValueChange={() => {}}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Elige programa" />
                </SelectTrigger>
                <SelectContent />
              </Select>
            </FilterField>
          )}

          {/* Producto — solo TT Shop, cascada del user */}
          {program === "tiktok_shop" ? (
            <FilterField label="Producto">
              <Select
                value={productId}
                onValueChange={setProductId}
                disabled={shopUser !== "all" && productsForUser.length === 0}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  {productsForUser.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FilterField>
          ) : (
            <FilterField label="Producto">
              <Select disabled value="all" onValueChange={() => {}}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent />
              </Select>
            </FilterField>
          )}
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

          {/* Editor Auto: coste por combinación de herramientas. Útil para
              decidir cuánto cobrar según las tools que activa cada user. */}
          {data.summary.by_tools_combo &&
            Object.keys(data.summary.by_tools_combo).length > 0 && (
              <BreakdownCard
                title="Editor Auto · Por combo de herramientas"
                data={data.summary.by_tools_combo}
                className="!grid-cols-1"
              />
            )}

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
                      <th className="px-3 py-2">tools</th>
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
                      <tr><td colSpan={8} className="p-4 text-center text-muted-foreground">
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

function FilterField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      {children}
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
  const date = j.started_at
    ? new Date(j.started_at * 1000).toLocaleString("es-ES", {
        day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
      })
    : "—";
  const tools = j.meta?.tools ?? [];
  return (
    <>
      <tr className="border-b cursor-pointer hover:bg-accent/30" onClick={() => setOpen(!open)}>
        <td className="px-3 py-2 font-mono">{j.job_id.slice(0, 8)}</td>
        <td className="px-3 py-2">{j.program}</td>
        <td className="px-3 py-2">{j.mode}</td>
        <td className="px-3 py-2">{j.user ?? "—"}</td>
        <td className="px-3 py-2">
          {tools.length > 0 ? (
            <span className="font-mono text-[10px]" title={tools.join(" + ")}>
              {tools.join(" + ")}
            </span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </td>
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
          <td colSpan={8} className="px-4 py-2">
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
