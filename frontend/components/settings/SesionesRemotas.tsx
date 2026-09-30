"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

/** Qué proyectos tienen sesión de Claude remoto abierta en el VPS.
 *
 *  Cada una gasta 75-220 MB aunque no se use, así que se marcan solo las que se
 *  van a usar. «Guardar» abre las marcadas y cierra las demás (no borra nada;
 *  se pueden volver a marcar cuando se quiera). Arrancan solas al reiniciar el
 *  servidor. Necesitan la sesión de Claude del VPS conectada (tarjeta de arriba).
 */
type Proyecto = { proyecto: string; activada: boolean; encendida: boolean; mb: number };
type Respuesta = { proyectos: Proyecto[] };

const KEY = ["claude-vps", "remotas"];

export function SesionesRemotas() {
  const qc = useQueryClient();
  const q = useQuery<Respuesta>({
    queryKey: KEY,
    queryFn: () => api.get<Respuesta>("/api/v1/claude-vps/remotas"),
    refetchInterval: 30_000,
    retry: false,
  });
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [tocado, setTocado] = useState(false);

  // Parte de lo que hay abierto; si el operador ya ha tocado, no se lo pisa el refresco.
  useEffect(() => {
    if (q.data && !tocado) {
      setMarcados(new Set(q.data.proyectos.filter((p) => p.activada).map((p) => p.proyecto)));
    }
  }, [q.data, tocado]);

  const guardar = useMutation<Respuesta, Error, string[]>({
    mutationFn: (proyectos) => api.post<Respuesta>("/api/v1/claude-vps/remotas", { proyectos }),
    onSuccess: (r) => {
      qc.setQueryData(KEY, r);
      setTocado(false);
      const abiertas = r.proyectos.filter((p) => p.encendida).length;
      toast.success(`Guardado: ${abiertas} sesión(es) abierta(s)`);
    },
    onError: () => toast.error("No se pudo aplicar el cambio en el servidor"),
  });

  const lista = q.data?.proyectos ?? [];
  const mbTotal = lista.filter((p) => p.encendida).reduce((n, p) => n + p.mb, 0);

  function alternar(p: string) {
    setTocado(true);
    setMarcados((prev) => {
      const s = new Set(prev);
      if (s.has(p)) s.delete(p);
      else s.add(p);
      return s;
    });
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">💻 Sesiones de Claude por proyecto</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs text-muted-foreground">
          Marca los proyectos en los que quieres poder abrir Claude remoto. Cada sesión gasta
          memoria aunque no la uses, así que deja solo las que vayas a usar.
          {mbTotal > 0 ? ` Ahora gastan unos ${mbTotal} MB.` : ""}
        </p>

        {q.isLoading ? (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando…
          </p>
        ) : q.isError ? (
          <p className="text-xs text-destructive">No se pudo consultar el servidor.</p>
        ) : (
          <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
            {lista.map((p) => (
              <li key={p.proyecto}>
                <label className="flex cursor-pointer items-center gap-2 rounded-md border border-border/60 px-2 py-1.5 hover:bg-accent/30">
                  <input
                    type="checkbox"
                    checked={marcados.has(p.proyecto)}
                    onChange={() => alternar(p.proyecto)}
                    className="h-4 w-4 shrink-0 accent-primary"
                  />
                  <span className="min-w-0 flex-1 truncate text-xs sm:text-sm">{p.proyecto}</span>
                  <span
                    className={`shrink-0 text-[10px] ${
                      p.encendida ? "text-emerald-500" : "text-muted-foreground"
                    }`}
                  >
                    {p.encendida ? `● abierta${p.mb ? ` · ${p.mb} MB` : ""}` : "○ cerrada"}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}

        <Button
          size="sm"
          disabled={!tocado || guardar.isPending || !lista.length}
          onClick={() => guardar.mutate([...marcados])}
        >
          {guardar.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Save className="mr-1.5 h-3.5 w-3.5" />
          )}
          Guardar
        </Button>
      </CardContent>
    </Card>
  );
}
