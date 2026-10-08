"use client";

import { ArrowUpRight, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";

interface ProductoLink {
  id: string;
  titulo: string;
  foto: string;
  enlace: string;
  tienda: "amazon" | "shein" | "";
}

interface DatosLinks {
  cuenta: string;
  productos: ProductoLink[];
  aviso_amazon: string;
}

const NOMBRE_TIENDA: Record<string, string> = { amazon: "Amazon", shein: "SHEIN" };

/** Minúsculas y sin acentos, para que «camiseta» encuentre «Camísetá». */
function normaliza(t: string): string {
  return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function LinksCuenta({ cuenta }: { cuenta: string }) {
  const [datos, setDatos] = useState<DatosLinks | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busca, setBusca] = useState("");

  useEffect(() => {
    let vivo = true;
    // Ruta relativa al host desde el que se abre (o la API local en dev):
    // vale servida desde cualquier dominio. Sin cookies ni API key.
    fetch(`${api.baseUrl}/api/v1/multiplataforma/links/${encodeURIComponent(cuenta)}`, {
      credentials: "omit",
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "Esta página no existe." : "No se ha podido cargar.");
        return (await r.json()) as DatosLinks;
      })
      .then((d) => vivo && setDatos(d))
      .catch((e: Error) => vivo && setError(e.message));
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

  return (
    <div className="min-h-[100dvh] bg-[#0d1117] text-slate-100 [color-scheme:dark]">
      <div className="pointer-events-none fixed inset-x-0 top-0 h-72 bg-[radial-gradient(60%_100%_at_50%_0%,rgba(20,184,166,0.18),transparent)]" />
      <main className="relative mx-auto w-full max-w-3xl px-4 pb-16 pt-[calc(2rem+env(safe-area-inset-top))]">
        <header className="mb-5 text-center">
          <h1 className="break-words text-2xl font-bold tracking-tight sm:text-3xl">
            {datos?.cuenta ?? (error ? "" : " ")}
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Lo que sale en mis vídeos. Toca un producto para verlo en la tienda.
          </p>
        </header>

        <div className="sticky top-[env(safe-area-inset-top)] z-10 -mx-4 mb-5 bg-[#0d1117]/90 px-4 py-2 backdrop-blur">
          <label className="relative block">
            <span className="sr-only">Buscar producto</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              type="search"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Busca el producto del vídeo…"
              className="w-full rounded-lg border border-slate-700/80 bg-slate-900/80 py-3 pl-10 pr-10 text-base text-slate-100 placeholder:text-slate-500 focus:border-teal-400/70 focus:outline-none focus:ring-2 focus:ring-teal-400/20"
            />
            {busca && (
              <button
                type="button"
                onClick={() => setBusca("")}
                aria-label="Borrar búsqueda"
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-400 hover:text-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </label>
        </div>

        {error && <p className="py-16 text-center text-sm text-slate-400">{error}</p>}

        {!datos && !error && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="aspect-[3/4] animate-pulse rounded-xl bg-slate-800/60" />
            ))}
          </div>
        )}

        {datos && visibles.length === 0 && (
          <p className="py-16 text-center text-sm text-slate-400">
            {busca ? `Nada con «${busca}». Prueba con otra palabra.` : "Todavía no hay productos."}
          </p>
        )}

        {visibles.length > 0 && (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {visibles.map((p) => (
              <li key={p.id}>
                <a
                  href={p.enlace}
                  target="_blank"
                  rel="nofollow sponsored noopener"
                  className="group flex h-full flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70 transition hover:border-teal-400/50 hover:bg-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/60"
                >
                  <div className="relative aspect-square w-full overflow-hidden bg-slate-800">
                    {/* eslint-disable-next-line @next/next/no-img-element -- foto servida por la API, sin optimizador */}
                    <img
                      src={`${api.baseUrl}${p.foto}`}
                      alt={p.titulo}
                      loading="lazy"
                      className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]"
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.visibility = "hidden";
                      }}
                    />
                  </div>
                  <div className="flex flex-1 items-start justify-between gap-2 p-3">
                    <div className="min-w-0">
                      <p className="line-clamp-2 break-words text-xs font-medium leading-snug text-slate-100 sm:text-sm">
                        {p.titulo}
                      </p>
                      {p.tienda && (
                        <p className="mt-1 text-[11px] text-slate-500">en {NOMBRE_TIENDA[p.tienda]}</p>
                      )}
                    </div>
                    <ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0 text-teal-400 transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                  </div>
                </a>
              </li>
            ))}
          </ul>
        )}

        {datos?.aviso_amazon && (
          <footer className="mt-10 border-t border-slate-800 pt-4 text-center text-[11px] leading-relaxed text-slate-500">
            {datos.aviso_amazon}
          </footer>
        )}
      </main>
    </div>
  );
}
