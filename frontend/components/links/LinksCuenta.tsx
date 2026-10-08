"use client";

import { ChevronRight, Search, X } from "lucide-react";
import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { api } from "@/lib/api";

interface ProductoLink {
  id: string;
  titulo: string;
  foto: string;
  enlace: string;
  tienda: "amazon" | "shein" | "";
}

interface Tema {
  fondo: string;
  acento: string;
  acento2: string;
  claro: boolean;
  lema: string;
}

interface DatosLinks {
  cuenta: string;
  tema?: Tema;
  banner?: string;
  logo?: string;
  portada?: string;
  /** Vertical 9:16: si está, es el fondo de toda la pantalla (móvil). */
  fondo?: string;
  productos: ProductoLink[];
  aviso_amazon: string;
}

const TEMA_DEFAULT: Tema = {
  fondo: "#0b1120",
  acento: "#14b8a6",
  acento2: "#5eead4",
  claro: false,
  lema: "Lo que sale en mis vídeos, con su enlace.",
};

const NOMBRE_TIENDA: Record<string, string> = { amazon: "Amazon", shein: "SHEIN" };

/** Con más productos que esto aparece el buscador. */
const MIN_BUSCADOR = 8;

/** Minúsculas y sin acentos, para que «camiseta» encuentre «Camísetá». */
function normaliza(t: string): string {
  return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** ¿Texto oscuro encima de este color? (luminancia relativa, WCAG). */
function esColorClaro(hex: string): boolean {
  const m = hex.replace("#", "").match(/^([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
  if (!m) return false;
  const [r = 0, g = 0, b = 0] = m.slice(1).map((h) => {
    const c = parseInt(h, 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.4;
}

function iniciales(nombre: string): string {
  return nombre
    .split(/[\s_]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

/** Página pública de enlaces: la marca de la cuenta (portada + logo + sus
 *  colores) para que quien llega desde la bio la reconozca, una franja de
 *  urgencia y los productos en LISTA (foto + texto + botón), que es lo que
 *  mejor cabe en un móvil. */
export function LinksCuenta({ cuenta }: { cuenta: string }) {
  const [datos, setDatos] = useState<DatosLinks | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busca, setBusca] = useState("");

  useEffect(() => {
    let vivo = true;
    // Ruta relativa al host desde el que se abre (o la API local en dev):
    // vale servida desde cualquier dominio. Sin cookies ni API key.
    // Con tiempo máximo y reintentos: si la petición se cuelga (un reinicio
    // del servidor, la red del navegador de Instagram), la página se quedaba
    // para siempre en «cargando».
    const url = `${api.baseUrl}/api/v1/multiplataforma/links/${encodeURIComponent(cuenta)}`;
    (async () => {
      for (let intento = 0; intento < 4 && vivo; intento++) {
        try {
          const r = await fetch(url, { credentials: "omit", signal: typeof AbortSignal.timeout === "function" ? AbortSignal.timeout(8000) : undefined });
          if (r.status === 404) throw new Error("Esta página no existe.");
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          const d = (await r.json()) as DatosLinks;
          if (vivo) setDatos(d);
          return;
        } catch (e) {
          if ((e as Error).message === "Esta página no existe.") {
            if (vivo) setError((e as Error).message);
            return;
          }
          await new Promise((res) => setTimeout(res, 1500 * (intento + 1)));
        }
      }
      if (vivo) setError("No se ha podido cargar. Vuelve a abrir el enlace en un momento.");
    })();
    return () => {
      vivo = false;
    };
  }, [cuenta]);

  const visibles = useMemo(() => {
    const lista = datos?.productos ?? [];
    const q = normaliza(busca.trim());
    if (!q) return lista;
    const palabras = q.split(/\s+/);
    return lista.filter((p) => {
      const t = normaliza(p.titulo);
      return palabras.every((w) => t.includes(w));
    });
  }, [datos, busca]);

  const tema = datos?.tema ?? TEMA_DEFAULT;
  const claro = tema.claro;
  const vars = {
    "--fondo": tema.fondo,
    "--acento": tema.acento,
    "--acento2": tema.acento2,
  } as CSSProperties;

  const texto = claro ? "text-stone-900" : "text-white";
  const textoSuave = claro ? "text-stone-600" : "text-white/65";
  // Con foto de fondo, tarjeta casi opaca: el título se tiene que leer igual
  // pase por encima de lo que pase.
  const tarjeta = claro
    ? "bg-white/90 border-stone-900/10 shadow-sm backdrop-blur-sm"
    : datos?.fondo
      ? "bg-black/60 border-white/15 backdrop-blur-sm"
      : "bg-white/[0.06] border-white/10";
  // Texto encima del acento (franja y botones): oscuro si el acento es claro.
  const sobreAcento = esColorClaro(tema.acento) ? "text-stone-950" : "text-white";
  // Todo texto que caiga sobre la foto de fondo va sobre este panel: el fondo
  // va lleno de objetos y, sin él, el texto se perdía en algunas zonas.
  const panel = datos?.fondo
    ? claro
      ? "bg-white/75 backdrop-blur-sm"
      : "bg-black/45 backdrop-blur-sm"
    : "";
  const textoPanel = claro ? "text-stone-700" : "text-white/85";
  const nombre = datos?.cuenta ?? "";
  const conBuscador = (datos?.productos.length ?? 0) > MIN_BUSCADOR;

  return (
    <div
      style={vars}
      className={`min-h-[100dvh] bg-[var(--fondo)] ${texto} ${claro ? "[color-scheme:light]" : "[color-scheme:dark]"}`}
    >
      {/* Fondo vertical de la marca: fijo detrás de todo (div fixed y no
          `background-attachment: fixed`, que iOS ignora). */}
      {datos?.fondo && (
        <div className="pointer-events-none fixed inset-0 z-0">
          {/* eslint-disable-next-line @next/next/no-img-element -- servida por la API */}
          <img src={`${api.baseUrl}${datos.fondo}`} alt="" className="h-full w-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[var(--fondo)]/40 to-[var(--fondo)]/80" />
        </div>
      )}

      {/* Portada de la marca, fundida con el fondo (solo sin fondo vertical) */}
      <div className={`relative w-full overflow-hidden ${datos?.fondo ? "h-28 sm:h-32" : "h-40 sm:h-56"}`}>
        {datos?.fondo ? null : datos?.portada ? (
          // eslint-disable-next-line @next/next/no-img-element -- servida por la API
          <img
            src={`${api.baseUrl}${datos.portada}`}
            alt=""
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="h-full w-full bg-[radial-gradient(70%_120%_at_50%_0%,var(--acento),transparent)] opacity-40" />
        )}
        {!datos?.fondo && (
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[var(--fondo)]" />
        )}
      </div>

      <main className="relative z-10 mx-auto -mt-14 w-full max-w-xl px-4 pb-16 sm:-mt-16">
        <header className="mb-5 flex flex-col items-center text-center">
          <div
            className="h-24 w-24 overflow-hidden rounded-full border-4 border-[var(--fondo)] bg-[var(--acento)] shadow-[0_0_0_2px_var(--acento),0_10px_30px_-8px_var(--acento)] sm:h-28 sm:w-28"
          >
            {datos?.logo ? (
              // eslint-disable-next-line @next/next/no-img-element -- servida por la API
              <img src={`${api.baseUrl}${datos.logo}`} alt={nombre} className="h-full w-full object-cover" />
            ) : (
              <span className="flex h-full w-full items-center justify-center text-2xl font-bold text-white">
                {iniciales(nombre)}
              </span>
            )}
          </div>
          {/* Panel translúcido: el fondo de la marca va lleno de objetos y el
              texto encima no se leía. */}
          <div
            className={`mt-3 rounded-2xl px-4 py-2 ${panel}`}
          >
            <h1 className="break-words text-2xl font-extrabold tracking-tight sm:text-3xl">
              {nombre || (error ? "" : " ")}
            </h1>
            {datos && <p className={`mt-0.5 text-sm font-medium ${textoPanel}`}>{tema.lema}</p>}
          </div>
        </header>

        {datos?.banner && (
          <div className="relative mb-5 rounded-xl">
            {/* El latido va en el halo, no en el texto: con `animate-pulse` sobre
                el texto, la mitad del tiempo se leía a medio apagar. */}
            <div className="absolute inset-0 animate-pulse rounded-xl bg-[var(--acento)] blur-md" />
            <div className={`relative rounded-xl bg-[var(--acento)] px-4 py-2.5 text-center text-sm font-bold ${sobreAcento}`}>
              {datos.banner}
            </div>
          </div>
        )}

        {conBuscador && (
          <div className="sticky top-[env(safe-area-inset-top)] z-10 -mx-4 mb-4 bg-[var(--fondo)]/90 px-4 py-2 backdrop-blur">
            <label className="relative block">
              <span className="sr-only">Buscar producto</span>
              <Search className={`pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 ${textoSuave}`} />
              <input
                type="search"
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="Busca el producto del vídeo…"
                className={`w-full rounded-xl border py-3 pl-10 pr-10 text-base focus:outline-none focus:ring-2 focus:ring-[var(--acento)] ${tarjeta} ${texto} placeholder:opacity-60`}
              />
              {busca && (
                <button
                  type="button"
                  onClick={() => setBusca("")}
                  aria-label="Borrar búsqueda"
                  className={`absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 ${textoSuave}`}
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </label>
          </div>
        )}

        {error && (
          <p className={`mx-auto my-12 w-fit rounded-xl px-4 py-3 text-center text-sm ${panel} ${textoPanel}`}>{error}</p>
        )}

        {!datos && !error && (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-24 animate-pulse rounded-2xl bg-white/10" />
            ))}
          </div>
        )}

        {datos && visibles.length === 0 && (
          <p className={`mx-auto my-12 w-fit rounded-xl px-4 py-3 text-center text-sm font-medium ${panel} ${textoPanel}`}>
            {busca ? `Nada con «${busca}». Prueba con otra palabra.` : "Muy pronto, los productos de mis vídeos aquí."}
          </p>
        )}

        {visibles.length > 0 && (
          <ul className="space-y-3">
            {visibles.map((p, i) => (
              <li key={p.id} className="relative">
                {/* El primero es el del último vídeo publicado: el que viene a
                    buscar casi todo el que llega desde la bio. */}
                {i === 0 && !busca && visibles.length > 1 && (
                  <span className={`absolute -top-2 right-3 z-10 rounded-full bg-[var(--acento2)] px-2.5 py-0.5 text-[11px] font-bold shadow ${esColorClaro(tema.acento2) ? "text-stone-950" : "text-white"}`}>
                    🆕 Último vídeo
                  </span>
                )}
                <a
                  href={p.enlace}
                  target="_blank"
                  rel="nofollow sponsored noopener"
                  className={`group flex items-center gap-3 rounded-2xl border p-2.5 transition active:scale-[0.99] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--acento)] ${tarjeta}`}
                >
                  <div className="h-20 w-20 shrink-0 overflow-hidden rounded-xl bg-white sm:h-24 sm:w-24">
                    {/* eslint-disable-next-line @next/next/no-img-element -- foto servida por la API, sin optimizador */}
                    <img
                      src={`${api.baseUrl}${p.foto}`}
                      alt={p.titulo}
                      loading="lazy"
                      className="h-full w-full object-cover"
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.visibility = "hidden";
                      }}
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 break-words text-sm font-semibold leading-snug">{p.titulo}</p>
                    <span className={`mt-2 inline-flex items-center gap-1 rounded-lg bg-[var(--acento)] px-3 py-1.5 text-xs font-bold ${sobreAcento}`}>
                      Ver oferta{p.tienda ? ` en ${NOMBRE_TIENDA[p.tienda]}` : ""}
                      <ChevronRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
                    </span>
                  </div>
                </a>
              </li>
            ))}
          </ul>
        )}

        {datos?.aviso_amazon && (
          // Obligatorio por el programa de afiliados, pero discreto: abajo del
          // todo, pequeño y sin recuadro.
          <footer className={`mt-8 px-2 text-center text-[10px] leading-snug opacity-70 ${claro ? "text-stone-700 [text-shadow:0_1px_2px_rgba(255,255,255,0.7)]" : "text-white/80 [text-shadow:0_1px_2px_rgba(0,0,0,0.5)]"}`}>
            {datos.aviso_amazon}
          </footer>
        )}
      </main>
    </div>
  );
}
