"use client";

import { RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/** Marcar un vídeo para rehacerlo, con la nota de qué falla.
 *
 *  La nota la lee quien rehace los clips —el operador o un agente por el MCP
 *  (`para_rehacer`)—, así que cuanto más concreta, mejor. Los motivos rápidos
 *  son los fallos que más se repiten al revisar (ver
 *  `src/agente_mcp/guias/comun/revision-calidad.md`): un toque los añade a la
 *  nota y luego se puede completar a mano.
 */
const MOTIVOS = [
  "El producto se mueve o cambia solo",
  "Aparecen piezas o detalles que no tiene",
  "Otro objeto parecido al lado",
  "La mano toca o coge el producto",
  "Tamaño o escala incorrectos",
  "Pantalla con apps o menús inventados",
  "La escena no pega con el producto",
  "Es para otro público (niños, etc.)",
];

export function RehacerDialog({
  abierto,
  onCerrar,
  titulo,
  onMarcar,
  motivos = MOTIVOS,
}: {
  abierto: boolean;
  onCerrar: () => void;
  /** Título del producto, para saber cuál se está marcando. */
  titulo: string;
  onMarcar: (nota: string) => void;
  /** Los motivos rápidos; por defecto, los de los clips de producto. */
  motivos?: string[];
}) {
  const [nota, setNota] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);

  // Cada vez que se abre, la nota empieza vacía.
  useEffect(() => {
    if (abierto) setNota("");
  }, [abierto]);

  const añadir = (m: string) => {
    setNota((prev) => {
      const t = prev.trim();
      if (t.toLowerCase().includes(m.toLowerCase())) return prev;
      return t ? `${t.replace(/[.;,]$/, "")}; ${m.toLowerCase()}` : m;
    });
    area.current?.focus();
  };

  const marcar = () => {
    onMarcar(nota.trim());
    onCerrar();
  };

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="w-[calc(100vw-2rem)] max-w-md max-h-[90vh] overflow-y-auto rounded-xl border-orange-500/40 p-4 sm:p-6">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base text-orange-500">
            <RotateCcw className="h-4 w-4" /> Rehacer este vídeo
          </DialogTitle>
          <DialogDescription className="break-words text-xs sm:text-sm">
            {titulo || "Producto"}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">¿Qué falla? Toca para añadirlo</p>
          <div className="flex flex-wrap gap-1.5">
            {motivos.map((m) => {
              const puesto = nota.toLowerCase().includes(m.toLowerCase());
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => añadir(m)}
                  className={`rounded-full border px-2.5 py-1 text-[11px] leading-tight transition sm:text-xs ${
                    puesto
                      ? "border-orange-500/60 bg-orange-500/15 text-orange-500"
                      : "border-border/60 text-muted-foreground hover:border-orange-500/50 hover:text-orange-500"
                  }`}
                >
                  {m}
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="nota-rehacer" className="text-xs font-medium text-muted-foreground">
            Nota (la lee quien lo rehaga)
          </label>
          <textarea
            id="nota-rehacer"
            ref={area}
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) marcar();
            }}
            rows={3}
            maxLength={400}
            placeholder="Ej.: es un organizador para niños, ponlo en un cuarto infantil"
            className="w-full resize-none rounded-lg border border-border/60 bg-background px-3 py-2 text-xs outline-none transition focus:border-orange-500/60 sm:text-sm"
          />
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <button
            type="button"
            onClick={onCerrar}
            className="rounded-lg border border-border/60 px-3 py-2 text-xs font-medium text-muted-foreground transition hover:text-foreground sm:text-sm"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={marcar}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-orange-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-orange-600 sm:text-sm"
          >
            <RotateCcw className="h-3.5 w-3.5" /> Marcar para rehacer
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
