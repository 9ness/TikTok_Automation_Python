"use client";

import { Link2, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useEsPro } from "@/lib/queries/auth";
import { useGuardarUrlProducto } from "@/lib/queries/nichoPovBof";

/** Abre la ficha del producto en TikTok Shop, y deja pegarla si falta.
 *
 *  Meter un producto en el escaparate es entrar en su ficha, y buscarla a mano
 *  cada vez es lo que hace lento ese trabajo — más con tres cuentas. Las fichas
 *  valen para todas las carpetas del producto y para los tres usuarios.
 *
 *  Verde = ya tiene ficha. Apagado = falta.
 *
 *  Apagado y siendo ADMIN, se pega aquí mismo. Antes había que irse a
 *  Configuración › Fichas de TikTok Shop, buscar el producto entre los de todo
 *  el catálogo y volver: para pegar una URL suelta mientras se repasa una
 *  carpeta, el viaje costaba más que el trabajo. Solo el admin porque es quien
 *  las consigue (gasta las llamadas de EchoTik) y una URL mal pegada la
 *  arrastran los tres nichos y las tres cuentas.
 *
 *  Se le pasa el producto (`source`/`folder`/`producto`) solo donde se quiere
 *  poder pegar; sin eso se comporta como siempre y solo abre.
 */
export function BotonUrl({
  url,
  source,
  folder,
  producto,
}: {
  url?: string | null;
  source?: string;
  folder?: string;
  producto?: string;
}) {
  const esPro = useEsPro();
  const guardar = useGuardarUrlProducto();
  const [pegando, setPegando] = useState(false);
  const [valor, setValor] = useState("");

  const puedePegar = !esPro && Boolean(source && folder && producto);

  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 rounded-md border border-emerald-500 bg-emerald-500/15 px-2 py-1 text-[11px] font-semibold text-emerald-500 transition hover:bg-emerald-500/25"
      >
        <Link2 className="h-3 w-3" /> URL
      </a>
    );
  }

  if (!pegando) {
    return (
      <button
        type="button"
        onClick={() => {
          if (!puedePegar) {
            toast.info("Sin ficha: pégala en Configuración › Fichas de TikTok Shop");
            return;
          }
          setPegando(true);
        }}
        className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition hover:border-foreground/40"
      >
        <Link2 className="h-3 w-3" /> URL
      </button>
    );
  }

  function grabar(texto = valor) {
    const limpia = texto.trim();
    if (!limpia) {
      setPegando(false);
      return;
    }
    guardar.mutate(
      { source: source!, folder: folder!, producto: producto!, url: limpia },
      {
        onSuccess: () => {
          // No se toca nada más: al invalidar, el producto vuelve con su
          // `product_url` y este mismo botón se pinta verde.
          toast.success("Ficha guardada");
          setPegando(false);
          setValor("");
        },
        onError: (e) => toast.error(e instanceof Error ? e.message : String(e)),
      },
    );
  }

  return (
    <span className="inline-flex min-w-0 items-center gap-1">
      <input
        // Se abre con el teclado puesto: se llega aquí para pegar, no para mirar.
        autoFocus
        value={valor}
        onChange={(e) => setValor(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") grabar();
          if (e.key === "Escape") setPegando(false);
        }}
        // Se pega del portapapeles y se guarda solo: pegar y tener que pulsar
        // otra cosa es el paso que sobra.
        onPaste={(e) => {
          const texto = e.clipboardData.getData("text").trim();
          if (!texto) return;
          e.preventDefault();
          setValor(texto);
          grabar(texto);
        }}
        placeholder="Pega la ficha…"
        className="min-w-0 flex-1 rounded-md border border-emerald-500/50 bg-transparent px-2 py-1 text-[11px] outline-none"
      />
      <button
        type="button"
        onClick={() => grabar()}
        disabled={guardar.isPending}
        aria-label="Guardar la ficha"
        className="shrink-0 rounded-md border border-emerald-500/50 px-1.5 py-1 text-emerald-500 disabled:opacity-50"
      >
        {guardar.isPending ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <Link2 className="h-3 w-3" />
        )}
      </button>
    </span>
  );
}
