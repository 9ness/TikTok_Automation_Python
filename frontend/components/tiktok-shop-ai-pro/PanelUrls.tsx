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
  useImportarUrls,
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

      <PegarUrlsEnLote source={source} />

      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {(sources.data?.items ?? []).map((s) => (
          <button
            key={s.slug}
            type="button"
            onClick={() => {
              setSource(s.slug);
              setAbierta("");
            }}
            className={`break-words leading-tight rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
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


/** Pegar de golpe las fichas sacadas del DOM de la web del curso.
 *
 *  Su página ya lleva el enlace de TikTok de cada producto, con la carpeta y
 *  el número al lado. Sacarlos con un pegote en la consola es gratis y son los
 *  ~310 de una vez; averiguarlos con EchoTik cuesta una llamada por producto
 *  y el plan gratis son 100 al mes.
 */
function PegarUrlsEnLote({ source }: { source: string }) {
  const importar = useImportarUrls();
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState("");

  // Su web es un ACORDEÓN: al abrir una carpeta cierra la anterior, así que
  // no vale con desplegarlas todas y leer al final — hay que leer cada una
  // mientras está abierta. Y el fichero en vez de `copy()`: con `await`,
  // Chrome envuelve el código y las utilidades de la consola dejan de existir.
  // Dos trampas de su web, las dos descubiertas a base de que no saliera:
  //  - Es un ACORDEÓN: al abrir una carpeta cierra la anterior, así que hay
  //    que leer cada una mientras está abierta, no desplegarlas todas.
  //  - Al abrir, REPINTA la lista entera: el `div.carp` que tuvieras en la
  //    mano queda descolgado y su `.prod` no llega nunca. Por eso se vuelve a
  //    buscar por índice en cada vuelta.
  // Y el fichero en vez de `copy()`: con `await`, Chrome envuelve el código y
  // las utilidades de la consola dejan de existir.
  const GUION = `const carps = () => [...document.querySelectorAll("div.carp")];
const filas = [];
for (let i = 0; i < carps().length; i++) {
  if (!carps()[i]?.querySelector(".prod")) {
    carps()[i]?.querySelector(".carp-head")?.click();
    for (let k = 0; k < 40 && !carps()[i]?.querySelector(".prod"); k++) {
      await new Promise((r) => setTimeout(r, 150));
    }
  }
  const c = carps()[i];
  if (!c) continue;
  const carpeta = c.querySelector(".carp-head b")?.textContent.trim();
  const antes = filas.length;
  c.querySelectorAll(".prod").forEach((p) => {
    filas.push({
      carpeta,
      producto: p.querySelector(".p-head b")?.textContent.trim(),
      url: p.querySelector("a.chip[href]")?.href ?? "",
      sin_stock: /sin\\s*stock/i.test(p.textContent || ""),
    });
  });
  console.log(carpeta, "· en esta:", filas.length - antes, "· total:", filas.length);
}
const a = document.createElement("a");
a.href = URL.createObjectURL(new Blob([JSON.stringify(filas)]));
a.download = "fichas.json";
a.click();
console.log("TOTAL", filas.length, "·", filas.filter((f) => f.url).length, "con enlace ·", filas.filter((f) => f.sin_stock).length, "sin stock");`;

  function enviar() {
    let filas: unknown[];
    try {
      filas = JSON.parse(texto);
    } catch {
      toast.error("Eso no es el JSON de la consola.");
      return;
    }
    if (!Array.isArray(filas) || !filas.length) {
      toast.error("El JSON no trae ninguna fila.");
      return;
    }
    importar.mutate(
      { source, filas },
      {
        onSuccess: (r) => {
          toast.success(
            `${r.guardados} ficha(s) en ${r.carpetas} carpeta(s)` +
              (r.con_id ? ` · ${r.con_id} con ID` : "") +
              (r.agotados ? ` · ${r.agotados} sin stock` : "") +
              (r.en_indice ? ` · ${r.en_indice} ya con texto` : ""),
          );
          // Callar esto dejaría enlaces sin guardar pareciendo que fue bien.
          if (r.descartadas?.length) {
            toast.warning(
              `${r.descartadas.length} enlace(s) no son de TikTok y no se han guardado: ` +
                r.descartadas.slice(0, 3).join(" · "),
              { duration: 12000 },
            );
          }
          if (r.sin_carpeta?.length) {
            toast.warning(
              `Sin guardar, no hay esa carpeta en el catálogo: ${r.sin_carpeta.join(", ")}`,
              { duration: 10000 },
            );
          }
          setTexto("");
          setAbierto(false);
        },
        onError: (e) =>
          toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  if (!abierto) {
    return (
      <button
        type="button"
        onClick={() => setAbierto(true)}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/40 bg-violet-500/5 px-3 py-1.5 text-[11px] font-medium text-violet-400 transition hover:border-violet-400"
      >
        <Link2 className="h-3.5 w-3.5" /> Pegar las fichas de la web de golpe
      </button>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-violet-500/40 bg-violet-500/5 p-2">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        En la web del curso, con las carpetas a la vista: F12 →{" "}
        <strong className="text-foreground">Console</strong> (si no deja pegar,
        escribe <code>allow pasting</code>) → pega esto y pulsa Enter. Va
        carpeta por carpeta (su web cierra una al abrir la siguiente) y al
        acabar te <strong className="text-foreground">descarga</strong>{" "}
        <code>fichas.json</code>. Ese fichero es el que se elige aquí abajo.
      </p>
      <pre className="max-h-32 overflow-auto rounded bg-background p-2 text-[10px] leading-tight text-muted-foreground">
        {GUION}
      </pre>
      <div className="grid grid-cols-2 gap-1.5">
        <button
          type="button"
          onClick={() => {
            navigator.clipboard.writeText(GUION);
            toast.success("Guion copiado");
          }}
          className="rounded-lg border border-border/60 px-2 py-1.5 text-[11px] transition hover:border-foreground/30"
        >
          Copiar el guion
        </button>
        <button
          type="button"
          onClick={() => setAbierto(false)}
          className="rounded-lg border border-border/60 px-2 py-1.5 text-[11px] text-muted-foreground transition hover:border-foreground/30"
        >
          Cerrar
        </button>
      </div>
      <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-[11px] transition hover:border-foreground/30">
        📄 Elegir el fichero <code>fichas.json</code>
        <input
          type="file"
          accept=".json,application/json"
          className="hidden"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) setTexto(await f.text());
          }}
        />
      </label>
      <textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        rows={4}
        placeholder="…o pega aquí el contenido a mano"
        className="w-full rounded-lg border border-border/60 bg-background p-2 text-[11px]"
      />
      <button
        type="button"
        disabled={!texto.trim() || importar.isPending}
        onClick={enviar}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-700 disabled:opacity-50"
      >
        {importar.isPending ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Guardando…
          </>
        ) : (
          <>Guardar en “{source}”</>
        )}
      </button>
    </div>
  );
}
