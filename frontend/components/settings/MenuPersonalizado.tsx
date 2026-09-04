"use client";

import { ChevronDown, ChevronUp, Eye, EyeOff, Loader2, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  NAV_FIJOS,
  aplicarPrefs,
  claveNav,
  navPara,
  type NavGroup,
} from "@/components/layout/Sidebar";
import { useMe } from "@/lib/queries/auth";
import {
  MENU_PREFS_VACIAS,
  useGuardarMenuPrefs,
  useMenuPrefs,
  type MenuPrefs,
} from "@/lib/queries/uiMenu";
import { cn } from "@/lib/utils";

/** Esconder y reordenar el menú lateral, por usuario.
 *
 *  Es la misma sidebar de al lado: se pinta desde `navPara` para que no haya
 *  dos listas que mantener. Aquí se ven TODAS las entradas —también las
 *  escondidas, en gris—, que es lo único que permite volver a encenderlas.
 *
 *  Cada toque guarda: son preferencias, no un formulario, y un botón de
 *  "guardar" es una pantalla más que se queda a medias.
 */
export function MenuPersonalizado() {
  const me = useMe();
  const consulta = useMenuPrefs();
  const guardar = useGuardarMenuPrefs();
  const prefs = consulta.data ?? MENU_PREFS_VACIAS;

  // El menú que le toca por ROL, sin filtrar por preferencias: lo escondido
  // tiene que seguir viéndose aquí para poder recuperarlo.
  const base = navPara(me.data?.rol);
  // …pero SÍ en el orden que tenga elegido, que es lo que se está tocando.
  const orden = ordenarComoLaSidebar(base, prefs);

  const oculto = (clave: string) => prefs.ocultos.includes(clave);

  function aplicar(cambio: Partial<MenuPrefs>) {
    guardar.mutate({ ...prefs, ...cambio });
  }

  function alternar(clave: string) {
    aplicar({
      ocultos: oculto(clave)
        ? prefs.ocultos.filter((k) => k !== clave)
        : [...prefs.ocultos, clave],
    });
  }

  function moverGrupo(clave: string, dir: -1 | 1) {
    const claves = orden.map(claveNav);
    aplicar({ orden_grupos: mover(claves, clave, dir) });
  }

  function moverItem(basePath: string, href: string, dir: -1 | 1) {
    const grupo = orden.find((n) => n.kind === "group" && n.basePath === basePath);
    if (!grupo || grupo.kind !== "group") return;
    const hrefs = grupo.items.map((i) => i.href);
    aplicar({
      orden_items: { ...prefs.orden_items, [basePath]: mover(hrefs, href, dir) },
    });
  }

  const escondidos = prefs.ocultos.length;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-base sm:text-lg">Mi menú</CardTitle>
        {guardar.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : escondidos > 0 ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 text-xs"
            onClick={() => aplicar({ ocultos: [] })}
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Ver todo ({escondidos})
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-[11px] leading-relaxed text-muted-foreground sm:text-xs">
          Esconde lo que no uses y coloca arriba lo de cada día. Es solo tu
          menú: no borra nada y las pantallas siguen estando si escribes la
          URL. Se guarda en tu cuenta, así que vale también en el móvil.
        </p>

        <ul className="space-y-2">
          {orden.map((node, i) => {
            const clave = claveNav(node);
            const apagado = oculto(clave);
            return (
              <li
                key={clave}
                className={cn(
                  "rounded-lg border border-border/60 p-2",
                  apagado && "opacity-50",
                )}
              >
                <Fila
                  label={node.kind === "single" ? node.item.label : node.title}
                  fuerte
                  apagado={apagado}
                  fijo={NAV_FIJOS.includes(clave)}
                  primero={i === 0}
                  ultimo={i === orden.length - 1}
                  onOcultar={() => alternar(clave)}
                  onSubir={() => moverGrupo(clave, -1)}
                  onBajar={() => moverGrupo(clave, 1)}
                />
                {node.kind === "group" && !apagado && (
                  <ul className="mt-1.5 space-y-1 border-l border-border/60 pl-2">
                    {node.items.map((item, j) => (
                      <li key={item.href}>
                        <Fila
                          label={item.label}
                          apagado={oculto(item.href)}
                          fijo={NAV_FIJOS.includes(item.href)}
                          primero={j === 0}
                          ultimo={j === node.items.length - 1}
                          onOcultar={() => alternar(item.href)}
                          onSubir={() => moverItem(node.basePath, item.href, -1)}
                          onBajar={() => moverItem(node.basePath, item.href, 1)}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function Fila({
  label,
  fuerte,
  apagado,
  fijo,
  primero,
  ultimo,
  onOcultar,
  onSubir,
  onBajar,
}: {
  label: string;
  fuerte?: boolean;
  apagado: boolean;
  fijo: boolean;
  primero: boolean;
  ultimo: boolean;
  onOcultar: () => void;
  onSubir: () => void;
  onBajar: () => void;
}) {
  return (
    <div className="flex items-center gap-1">
      <span
        className={cn(
          "min-w-0 flex-1 truncate text-xs sm:text-sm",
          fuerte && "font-semibold",
          apagado && "line-through",
        )}
      >
        {label}
      </span>
      {/* Flechas y no arrastrar: esto se toca desde el móvil y un
          drag-and-drop dentro de una lista que ya hace scroll es pelearse. */}
      <button
        type="button"
        disabled={primero}
        onClick={onSubir}
        aria-label={`Subir ${label}`}
        className="rounded p-1 text-muted-foreground transition hover:bg-accent/40 hover:text-foreground disabled:opacity-25"
      >
        <ChevronUp className="h-4 w-4" />
      </button>
      <button
        type="button"
        disabled={ultimo}
        onClick={onBajar}
        aria-label={`Bajar ${label}`}
        className="rounded p-1 text-muted-foreground transition hover:bg-accent/40 hover:text-foreground disabled:opacity-25"
      >
        <ChevronDown className="h-4 w-4" />
      </button>
      <button
        type="button"
        disabled={fijo}
        onClick={onOcultar}
        aria-label={apagado ? `Mostrar ${label}` : `Ocultar ${label}`}
        title={fijo ? "Este no se puede esconder: es desde donde se recupera el resto" : undefined}
        className={cn(
          "rounded p-1 transition hover:bg-accent/40 disabled:opacity-25",
          apagado ? "text-muted-foreground" : "text-emerald-500",
        )}
      >
        {apagado ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

/** El menú completo, en el orden en que la sidebar lo va a pintar.
 *
 *  `aplicarPrefs` quita lo escondido, y aquí hacen falta TODAS las entradas,
 *  así que se le pasa el orden con la lista de ocultos vacía.
 */
function ordenarComoLaSidebar(nav: NavGroup[], prefs: MenuPrefs): NavGroup[] {
  return aplicarPrefs(nav, { ...prefs, ocultos: [] });
}

/** Sube o baja una clave dentro de la lista, sin sacarla de ella. */
function mover(claves: string[], clave: string, dir: -1 | 1): string[] {
  const i = claves.indexOf(clave);
  const j = i + dir;
  if (i === -1 || j < 0 || j >= claves.length) return claves;
  const copia = [...claves];
  const aqui = copia[i]!;
  copia[i] = copia[j]!;
  copia[j] = aqui;
  return copia;
}
