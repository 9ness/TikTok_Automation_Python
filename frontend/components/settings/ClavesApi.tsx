"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";

/** Claves API de todos los proyectos del VPS (`~/proyectos/*`), sin terminal.
 *
 *  La versión web de `clave`: se guarda en el `.env.local` del proyecto (o
 *  `.env` si solo hay ese), se niega si no está en su `.gitignore` y prueba la
 *  clave contra su API. La clave solo viaja de ida: el listado enseña nombre y
 *  últimos 4, nunca el valor.
 */
type Variable = { nombre: string; mascara: string };
type Proyecto = {
  proyecto: string;
  fichero: string;
  existe: boolean;
  ignorado: boolean | null;
  variables: Variable[];
};
type Respuesta = { proyectos: Proyecto[] };
type Guardado = {
  proyecto: string;
  variable: string;
  fichero: string;
  accion: string;
  mascara: string;
  prueba: number | "red" | null;
};

const KEY = ["claves-api"];
const VARIABLES = ["ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_PAID", "OPENAI_API_KEY"];
const OTRA = "__otra__";
const SELECT =
  "h-9 w-full rounded-md border border-input bg-background px-2 text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-ring";

function textoPrueba(p: Guardado["prueba"]): { texto: string; ok: boolean | null } {
  if (p === null) return { texto: "sin prueba (variable desconocida)", ok: null };
  if (p === "red") return { texto: "no se pudo llamar a la API", ok: false };
  if (p === 200) return { texto: "la clave funciona (HTTP 200)", ok: true };
  return { texto: `la API responde HTTP ${p}: revisa la clave`, ok: false };
}

export function ClavesApi() {
  const qc = useQueryClient();
  const q = useQuery<Respuesta>({
    queryKey: KEY,
    queryFn: () => api.get<Respuesta>("/api/v1/claves"),
    retry: false,
  });
  const [proyecto, setProyecto] = useState("");
  const [variable, setVariable] = useState<string>("ANTHROPIC_API_KEY");
  const [otra, setOtra] = useState("");
  const [valor, setValor] = useState("");
  const [ultimo, setUltimo] = useState<Guardado | null>(null);

  const lista = q.data?.proyectos ?? [];
  const elegido = lista.find((p) => p.proyecto === proyecto);
  const nombreVar = (variable === OTRA ? otra : variable).trim().toUpperCase();
  const varValida = /^[A-Z_][A-Z0-9_]*$/.test(nombreVar);
  const bloqueado = elegido?.ignorado === false;

  const guardar = useMutation<Guardado, Error, void>({
    mutationFn: () =>
      api.post<Guardado>("/api/v1/claves", { proyecto, variable: nombreVar, valor }),
    onSuccess: (r) => {
      setValor("");
      setUltimo(r);
      qc.invalidateQueries({ queryKey: KEY });
      toast.success(`${r.variable} ${r.accion} en ${r.proyecto}/${r.fichero}`);
    },
    onError: (e) => {
      setValor("");
      toast.error(e instanceof ApiError ? e.message : "No se pudo guardar la clave");
    },
  });

  const prueba = ultimo ? textoPrueba(ultimo.prueba) : null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">🔑 Claves API</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs text-muted-foreground">
          Guarda una clave en el <code>.env.local</code> de cualquier proyecto del VPS. Las de
          Anthropic, una por app con su nombre (fitness, masterpicks…). En producción va también en
          Vercel con el mismo nombre de variable.
        </p>

        {q.isLoading ? (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando…
          </p>
        ) : q.isError ? (
          <p className="text-xs text-destructive">No se pudo consultar el servidor.</p>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <select
                className={SELECT}
                value={proyecto}
                onChange={(e) => {
                  setProyecto(e.target.value);
                  setUltimo(null);
                }}
              >
                <option value="">Proyecto…</option>
                {lista.map((p) => (
                  <option key={p.proyecto} value={p.proyecto}>
                    {p.proyecto}
                  </option>
                ))}
              </select>
              <select
                className={SELECT}
                value={variable}
                onChange={(e) => setVariable(e.target.value)}
              >
                {VARIABLES.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
                <option value={OTRA}>Otra…</option>
              </select>
            </div>

            {variable === OTRA && (
              <Input
                placeholder="NOMBRE_DE_LA_VARIABLE"
                value={otra}
                onChange={(e) => setOtra(e.target.value)}
                className="text-xs sm:text-sm"
                autoCapitalize="characters"
                spellCheck={false}
              />
            )}

            {elegido && (
              <div className="rounded-md border border-border/60 p-2 text-xs">
                <p className="break-words text-muted-foreground">
                  Fichero: <code>{elegido.fichero}</code>
                  {!elegido.existe && " (se crea)"}
                  {elegido.ignorado === false && (
                    <span className="text-destructive">
                      {" "}
                      · NO está en el .gitignore: no se puede guardar aquí
                    </span>
                  )}
                  {elegido.ignorado === null && " · no es un repo git"}
                </p>
                {elegido.variables.length ? (
                  <ul className="mt-1.5 space-y-0.5">
                    {elegido.variables.map((v) => (
                      <li key={v.nombre} className="flex items-center justify-between gap-2">
                        <span className="min-w-0 truncate font-medium">{v.nombre}</span>
                        <span className="shrink-0 text-muted-foreground">{v.mascara}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-muted-foreground">Sin variables todavía.</p>
                )}
              </div>
            )}

            <form
              className="flex flex-col gap-2 sm:flex-row"
              onSubmit={(e) => {
                e.preventDefault();
                guardar.mutate();
              }}
            >
              <Input
                type="password"
                autoComplete="off"
                placeholder="Pega la clave"
                value={valor}
                onChange={(e) => setValor(e.target.value)}
                className="text-xs sm:text-sm"
              />
              <Button
                type="submit"
                size="sm"
                className="h-9 shrink-0"
                disabled={!proyecto || !varValida || !valor.trim() || bloqueado || guardar.isPending}
              >
                {guardar.isPending ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="mr-1.5 h-3.5 w-3.5" />
                )}
                Guardar
              </Button>
            </form>

            {ultimo && prueba && (
              <p
                className={`break-words text-xs ${
                  prueba.ok === true
                    ? "text-emerald-500"
                    : prueba.ok === false
                      ? "text-destructive"
                      : "text-muted-foreground"
                }`}
              >
                {prueba.ok === true ? "✓" : prueba.ok === false ? "⚠" : "·"} {ultimo.variable} (
                {ultimo.mascara}) {ultimo.accion}: {prueba.texto}.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
