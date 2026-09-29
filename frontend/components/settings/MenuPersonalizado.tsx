"use client";

import {
  DndContext,
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ChevronDown, ChevronRight, Eye, EyeOff, GripVertical, Loader2, RotateCcw } from "lucide-react";
import { useState, type ReactNode } from "react";

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
 *
 *  Se ordena ARRASTRANDO por el asa (⋮⋮), con ratón o con el dedo. Solo el asa
 *  arrastra (con `touch-action: none`): así el resto de la fila sigue dejando
 *  hacer scroll en el móvil, que es donde un drag-and-drop en una lista larga
 *  se pelea con el gesto de desplazar la página.
 *
 *  Va CERRADO por defecto: es de las pocas cosas de Ajustes que se tocan una
 *  vez y la lista entera ocupa varias pantallas.
 */
export function MenuPersonalizado() {
  const me = useMe();
  const consulta = useMenuPrefs();
  const guardar = useGuardarMenuPrefs();
  const prefs = consulta.data ?? MENU_PREFS_VACIAS;
  const [abierto, setAbierto] = useState(false);

  // Ratón: se empieza a arrastrar tras mover 4 px (un clic no es un arrastre).
  // Dedo: hace falta mantener 150 ms sobre el asa, para no confundirlo con
  // tocar. Teclado: flechas, para quien no pueda arrastrar.
  const sensores = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

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

  function soltarGrupo(e: DragEndEvent) {
    const claves = orden.map(claveNav);
    const nuevo = reordenar(claves, e);
    if (nuevo) aplicar({ orden_grupos: nuevo });
  }

  function soltarItem(basePath: string, hrefs: string[], e: DragEndEvent) {
    const nuevo = reordenar(hrefs, e);
    if (nuevo) aplicar({ orden_items: { ...prefs.orden_items, [basePath]: nuevo } });
  }

  const escondidos = prefs.ocultos.length;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <button
          type="button"
          onClick={() => setAbierto((v) => !v)}
          aria-expanded={abierto}
          className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
        >
          {abierto ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <CardTitle className="text-base sm:text-lg">Mi menú</CardTitle>
          {!abierto && escondidos > 0 ? (
            <span className="ml-1 rounded-full bg-muted px-1.5 py-px text-[10px] text-muted-foreground">
              {escondidos} escondido{escondidos === 1 ? "" : "s"}
            </span>
          ) : null}
        </button>
        {guardar.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : abierto && escondidos > 0 ? (
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
      {abierto ? (
        <CardContent className="space-y-3">
          <p className="text-[11px] leading-relaxed text-muted-foreground sm:text-xs">
            Esconde lo que no uses y coloca arriba lo de cada día: agarra el asa{" "}
            <GripVertical className="inline h-3 w-3 align-[-2px]" /> y arrastra (con el dedo,
            mantén pulsado un momento). Es solo tu menú: no borra nada y las pantallas siguen
            estando si escribes la URL. Se guarda en tu cuenta, así que vale también en el
            móvil.
          </p>

          <DndContext sensors={sensores} collisionDetection={closestCenter} onDragEnd={soltarGrupo}>
            <SortableContext items={orden.map(claveNav)} strategy={verticalListSortingStrategy}>
              <ul className="space-y-2">
                {orden.map((node) => {
                  const clave = claveNav(node);
                  const apagado = oculto(clave);
                  return (
                    <Ordenable key={clave} id={clave} className="rounded-lg border border-border/60 p-2">
                      {(asa) => (
                        <>
                          <Fila
                            asa={asa}
                            label={node.kind === "single" ? node.item.label : node.title}
                            fuerte
                            apagado={apagado}
                            fijo={NAV_FIJOS.includes(clave)}
                            onOcultar={() => alternar(clave)}
                          />
                          {node.kind === "group" && !apagado && (
                            <DndContext
                              sensors={sensores}
                              collisionDetection={closestCenter}
                              onDragEnd={(e) =>
                                soltarItem(node.basePath, node.items.map((i) => i.href), e)
                              }
                            >
                              <SortableContext
                                items={node.items.map((i) => i.href)}
                                strategy={verticalListSortingStrategy}
                              >
                                <ul className="mt-1.5 space-y-1 border-l border-border/60 pl-2">
                                  {node.items.map((item) => (
                                    <Ordenable key={item.href} id={item.href}>
                                      {(asaItem) => (
                                        <Fila
                                          asa={asaItem}
                                          label={item.label}
                                          apagado={oculto(item.href)}
                                          fijo={NAV_FIJOS.includes(item.href)}
                                          onOcultar={() => alternar(item.href)}
                                        />
                                      )}
                                    </Ordenable>
                                  ))}
                                </ul>
                              </SortableContext>
                            </DndContext>
                          )}
                        </>
                      )}
                    </Ordenable>
                  );
                })}
              </ul>
            </SortableContext>
          </DndContext>
        </CardContent>
      ) : null}
    </Card>
  );
}

/** Lo que se le pasa a la fila para que pinte el asa de arrastre. */
type Asa = { atributos: object; escuchas: object | undefined; arrastrando: boolean };

/** Un `<li>` que se puede reordenar. El hijo recibe el asa y decide dónde ponerla. */
function Ordenable({
  id,
  className,
  children,
}: {
  id: string;
  className?: string;
  children: (asa: Asa) => ReactNode;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(className, isDragging && "relative z-10 bg-background shadow-lg ring-1 ring-primary/40")}
    >
      {children({ atributos: attributes, escuchas: listeners, arrastrando: isDragging })}
    </li>
  );
}

function Fila({
  asa,
  label,
  fuerte,
  apagado,
  fijo,
  onOcultar,
}: {
  asa: Asa;
  label: string;
  fuerte?: boolean;
  apagado: boolean;
  fijo: boolean;
  onOcultar: () => void;
}) {
  return (
    <div className={cn("flex items-center gap-1", apagado && "opacity-50")}>
      {/* El asa es lo ÚNICO que arrastra, y lleva `touch-action: none` para que
          en el móvil el dedo sobre ella mueva la fila y no la página. */}
      <button
        type="button"
        aria-label={`Mover ${label}`}
        className="cursor-grab touch-none rounded p-1.5 text-muted-foreground transition hover:bg-accent/40 hover:text-foreground active:cursor-grabbing"
        {...asa.atributos}
        {...(asa.escuchas ?? {})}
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <span
        className={cn(
          "min-w-0 flex-1 truncate text-xs sm:text-sm",
          fuerte && "font-semibold",
          apagado && "line-through",
        )}
      >
        {label}
      </span>
      <button
        type="button"
        disabled={fijo}
        onClick={onOcultar}
        aria-label={apagado ? `Mostrar ${label}` : `Ocultar ${label}`}
        title={fijo ? "Este no se puede esconder: es desde donde se recupera el resto" : undefined}
        className={cn(
          "rounded p-1.5 transition hover:bg-accent/40 disabled:opacity-25",
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

/** El orden nuevo tras soltar una fila, o `null` si no se movió de sitio. */
function reordenar(claves: string[], e: DragEndEvent): string[] | null {
  const { active, over } = e;
  if (!over || active.id === over.id) return null;
  const desde = claves.indexOf(String(active.id));
  const hasta = claves.indexOf(String(over.id));
  if (desde === -1 || hasta === -1) return null;
  return arrayMove(claves, desde, hasta);
}
