"use client";

import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useSetEstado } from "@/lib/queries/nichoPovBof";

/** Escribir el precio cuando la ficha no se deja leer.
 *
 *  El precio no es un adorno: por encima de 40 € el vídeo lleva el guion de
 *  plazos y se monta con DOS clips. Si la captura de la ficha falta —pasa con
 *  los productos que sube el operador y con los que vienen de "Top vendidos"
 *  copiados sin ella—, el producto se queda en "precio sin detectar" y se
 *  montaría como uno barato sin que nadie se entere.
 */
export function PrecioAMano({
  source,
  folder,
  producto,
}: {
  source: string;
  folder: string;
  producto: string;
}) {
  const setEstado = useSetEstado();
  const [abierto, setAbierto] = useState(false);
  const [valor, setValor] = useState("");

  if (!abierto) {
    return (
      <button
        type="button"
        onClick={() => setAbierto(true)}
        className="text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
      >
        precio sin detectar · ponlo
      </button>
    );
  }
  return (
    <span className="flex items-center gap-1">
      <input
        type="number"
        inputMode="decimal"
        step="0.01"
        autoFocus
        value={valor}
        onChange={(e) => setValor(e.target.value)}
        placeholder="€"
        className="w-16 rounded border border-border/60 bg-transparent px-1 py-0.5 text-[10px]"
      />
      <button
        type="button"
        disabled={setEstado.isPending || !valor}
        onClick={() =>
          setEstado.mutate(
            { source, folder, producto, precio: Number(valor.replace(",", ".")) },
            {
              onSuccess: () => {
                toast.success("Precio guardado");
                setAbierto(false);
              },
              onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
            },
          )
        }
        className="rounded bg-emerald-500 px-1.5 py-0.5 font-semibold text-white disabled:opacity-50"
      >
        ok
      </button>
      <button
        type="button"
        onClick={() => setAbierto(false)}
        className="text-muted-foreground hover:text-foreground"
      >
        ×
      </button>
    </span>
  );
}
