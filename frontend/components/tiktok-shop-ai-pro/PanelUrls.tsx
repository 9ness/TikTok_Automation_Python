"use client";

import { Check, Link2, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import {
  buildCleanPhotoDownloadUrl,
  useGuardarUrlProducto,
  useSources,
  useUrlsCatalogo,
} from "@/lib/queries/nichoPovBof";

/** Pegar las fichas de TikTok Shop de un catálogo entero, tienda por tienda.
 *
 *  Meter un producto en el escaparate es entrar en su ficha de la app, y
 *  buscarla a mano cada vez es lo que hace lento el trabajo — más aún con tres
 *  cuentas. Aquí se pegan todas una vez: la ficha es del PRODUCTO, así que vale
 *  para todas sus carpetas, para todos los nichos y para los tres usuarios.
 *
 *  Por tienda porque así se trabaja: se abre la tienda en la app y se van
 *  copiando sus productos seguidos.
 */
export function PanelUrls() {
  const sources = useSources();
  const [source, setSource] = useState("aleatorios_2");
  const [abierta, setAbierta] = useState("");
  const datos = useUrlsCatalogo(source);
  const guardar = useGuardarUrlProducto();

  return (
    <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
      <div className="flex items-center gap-2">
        <Link2 className="h-4 w-4 shrink-0 text-emerald-500" />
        <p className="text-sm font-semibold">Fichas de TikTok Shop</p>
        {datos.data && (
          <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            {datos.data.con_url}/{datos.data.total} con ficha
          </span>
        )}
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Cada tienda va ordenada de más caro a más barato (los que no tienen
        precio leído, al final). Pega aquí el enlace de cada producto en la app
        de TikTok Shop. Después,
        en cada nicho, el botón 🔗 abre la ficha directamente — que es lo único
        que hace falta para meterlo en el escaparate. Se guarda por producto, así
        que sirve para todas sus carpetas y para las cuentas de Mauro y Ana.
      </p>

      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {(sources.data?.items ?? []).map((s) => (
          <button
            key={s.slug}
            type="button"
            onClick={() => {
              setSource(s.slug);
              setAbierta("");
            }}
            className={`truncate rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
              source === s.slug
                ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
                : "border-border/60 text-muted-foreground hover:border-foreground/40"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {datos.isLoading && (
        <p className="flex items-center justify-center gap-2 py-3 text-[11px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Leyendo el catálogo…
        </p>
      )}

      <div className="space-y-1.5">
        {(datos.data?.tiendas ?? []).map((t) => (
          <div key={t.tienda} className="rounded-lg border border-border/60">
            <button
              type="button"
              onClick={() => setAbierta(abierta === t.tienda ? "" : t.tienda)}
              className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-[11px]"
            >
              <span className="min-w-0 flex-1 truncate font-medium">{t.tienda}</span>
              <span
                className={`shrink-0 font-semibold ${
                  t.con_url === t.total ? "text-emerald-500" : "text-muted-foreground"
                }`}
              >
                {t.con_url}/{t.total}
              </span>
            </button>
            {abierta === t.tienda && (
              <div className="space-y-1.5 border-t border-border/60 p-2">
                {t.items.map((p) => (
                  <FilaUrl
                    key={p.clave}
                    titulo={p.titulo}
                    tituloTikTok={p.titulo_tiktok_completo}
                    tienda={p.tienda}
                    precio={p.precio}
                    precioLista={p.precio_lista}
                    foto={buildCleanPhotoDownloadUrl(p.source, p.folder, p.producto, "limpia", 120)}
                    fotoGrande={buildCleanPhotoDownloadUrl(p.source, p.folder, p.producto, "limpia", 900)}
                    fotoFicha={buildCleanPhotoDownloadUrl(p.source, p.folder, p.producto, "ficha", 900)}
                    carpetas={p.carpetas.length}
                    url={p.url}
                    guardando={guardar.isPending}
                    onGuardar={(url) =>
                      guardar.mutate(
                        {
                          source: p.source,
                          folder: p.folder,
                          producto: p.producto,
                          url,
                        },
                        {
                          onSuccess: () => toast.success(url ? "Ficha guardada" : "Ficha quitada"),
                          onError: (e) =>
                            toast.error(e instanceof ApiError ? e.message : String(e)),
                        },
                      )
                    }
                  />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

/** Una línea: el producto, su enlace y el botón de guardar. */
function FilaUrl({
  titulo,
  tituloTikTok,
  tienda,
  precio,
  precioLista,
  foto,
  fotoGrande,
  fotoFicha,
  carpetas,
  url,
  guardando,
  onGuardar,
}: {
  titulo: string;
  /** El literal de la ficha: es lo que se busca en la app de TikTok. */
  tituloTikTok: string;
  tienda: string;
  /** Precio de la ficha; 0 si no se pudo leer. */
  precio: number;
  /** El de antes del descuento (0 si no lo hay): se enseña tachado. */
  precioLista: number;
  foto: string;
  /** La misma foto en grande y la captura de la ficha, para el visor. */
  fotoGrande: string;
  fotoFicha: string;
  /** En cuántas carpetas sale el mismo producto (la ficha vale para todas). */
  carpetas: number;
  url: string;
  guardando: boolean;
  onGuardar: (url: string) => void;
}) {
  const [valor, setValor] = useState(url);
  const [verFoto, setVerFoto] = useState(false);
  useEffect(() => setValor(url), [url]);
  const cambiado = valor.trim() !== url;

  return (
    <div className="space-y-1 rounded-md border border-border/60 p-1.5">
      <div className="flex gap-1.5">
        {/* La foto limpia: es lo que deja reconocer el producto de un vistazo
            cuando la tienda tiene quince sérums que se llaman casi igual. */}
        {/* Se toca y se ve en grande, como en las fichas de los nichos: en un
            sello de 48 px no se distingue un sérum de otro. */}
        <button type="button" onClick={() => setVerFoto(true)} className="shrink-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={foto}
            alt={titulo}
            loading="lazy"
            className="h-12 w-12 rounded object-cover"
          />
        </button>
        <div className="min-w-0 flex-1 space-y-1">
          <p className="line-clamp-2 text-[10px] leading-tight">
            {/* Los dos precios, como en las fichas de los nichos: el de antes
                tachado y el que se paga en negrita. */}
            {precioLista > precio && (
              <span className="mr-1 font-mono text-muted-foreground line-through">
                {precioLista.toFixed(2).replace(".", ",")} €
              </span>
            )}
            {precio > 0 && (
              <span className="mr-1 font-mono font-semibold">
                {precio.toFixed(2).replace(".", ",")} €
              </span>
            )}
            {titulo.split("\n").join(" ")}
            {carpetas > 1 && (
              <span className="ml-1 text-muted-foreground">· en {carpetas} carpetas</span>
            )}
          </p>
          {/* Para buscarlo en la app: el título literal y la tienda. */}
          <div className="flex flex-wrap gap-1">
            <CopyChip label="🔎 Título" text={tituloTikTok} siempre />
            <CopyChip label="🏪 Tienda" text={tienda} siempre />
          </div>
        </div>
      </div>
      <div className="flex gap-1">
        <input
          value={valor}
          onChange={(e) => setValor(e.target.value)}
          placeholder="https://www.tiktok.com/view/product/…"
          className={`min-w-0 flex-1 rounded border bg-background px-1.5 py-1 text-[10px] ${
            url ? "border-emerald-500/50" : "border-border/60"
          }`}
        />
        <button
          type="button"
          disabled={guardando || !cambiado}
          onClick={() => onGuardar(valor.trim())}
          className="shrink-0 rounded border border-border/60 px-2 text-[10px] font-semibold transition hover:border-foreground/40 disabled:opacity-40"
        >
          {url && !cambiado ? <Check className="h-3 w-3 text-emerald-500" /> : "Guardar"}
        </button>
      </div>

      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={titulo.split("\n").join(" ")}
        urlLimpia={fotoGrande}
        urlTitulo={fotoFicha}
      />
    </div>
  );
}
