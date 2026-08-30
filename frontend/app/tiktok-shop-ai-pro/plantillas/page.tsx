"use client";

import { Check, Copy, MessageSquareText, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  type Plantilla,
  useGuardarPlantillas,
  usePlantillas,
  useRestaurarPlantillas,
} from "@/lib/queries/plantillas";

/** Los huecos que se rellenan antes de copiar.
 *
 *  Solo la cuenta es fija; el producto NO hace falta porque al vendedor se le
 *  escribe desde la ficha y el chat ya dice de cuál se habla. Se deja
 *  disponible por si alguna plantilla propia lo necesita, pero la de fábrica
 *  no lo usa: un hueco de menos es un error de menos al enviar.
 */
const HUECOS = [
  { clave: "CUENTA", label: "Tu cuenta", ejemplo: "@micuenta" },
  { clave: "PRODUCTO", label: "Producto (opcional)", ejemplo: "este producto" },
] as const;

function rellenar(texto: string, valores: Record<string, string>): string {
  let salida = texto;
  for (const { clave, ejemplo } of HUECOS) {
    const valor = (valores[clave] || "").trim();
    salida = salida.replaceAll(`{{${clave}}}`, valor || ejemplo);
  }
  return salida;
}

function TarjetaPlantilla({
  plantilla,
  valores,
  onCambiar,
  onBorrar,
}: {
  plantilla: Plantilla;
  valores: Record<string, string>;
  onCambiar: (p: Plantilla) => void;
  onBorrar: () => void;
}) {
  const [editando, setEditando] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const final = rellenar(plantilla.texto, valores);

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(final);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1800);
    } catch {
      toast.error("El navegador no dejó copiar. Selecciona el texto a mano.");
    }
  };

  return (
    <section className="space-y-2 rounded-lg border border-border/60 bg-card p-3">
      <div className="flex items-start gap-2">
        {editando ? (
          <input
            value={plantilla.titulo}
            onChange={(e) => onCambiar({ ...plantilla, titulo: e.target.value })}
            className="flex-1 rounded-md border border-border/60 bg-background px-2 py-1 text-sm font-semibold"
            placeholder="Título"
          />
        ) : (
          <h2 className="flex-1 break-words text-sm font-semibold sm:text-base">
            {plantilla.titulo}
          </h2>
        )}
        <button
          type="button"
          onClick={() => setEditando((v) => !v)}
          className="shrink-0 rounded-md border border-border/60 px-2 py-1 text-[11px] transition hover:border-foreground/40"
        >
          {editando ? "Listo" : "Editar"}
        </button>
      </div>

      {editando ? (
        <input
          value={plantilla.nota}
          onChange={(e) => onCambiar({ ...plantilla, nota: e.target.value })}
          className="w-full rounded-md border border-border/60 bg-background px-2 py-1 text-[11px]"
          placeholder="Nota: para qué sirve y qué rellenar antes de mandarla"
        />
      ) : (
        plantilla.nota && (
          <p className="text-[11px] leading-relaxed text-muted-foreground">{plantilla.nota}</p>
        )
      )}

      {editando ? (
        <>
          <textarea
            value={plantilla.texto}
            onChange={(e) => onCambiar({ ...plantilla, texto: e.target.value })}
            rows={14}
            className="w-full rounded-md border border-border/60 bg-background p-2 font-mono text-[11px] leading-relaxed"
          />
          <p className="text-[10px] text-muted-foreground">
            Huecos disponibles: {HUECOS.map((h) => `{{${h.clave}}}`).join(" · ")}
          </p>
        </>
      ) : (
        // `whitespace-pre-wrap`: el mensaje va por párrafos y viñetas, y sin
        // esto se veía como un churro de una línea — justo lo que hay que
        // revisar antes de enviarlo.
        <p className="whitespace-pre-wrap rounded-md bg-muted/40 p-2 text-[11px] leading-relaxed">
          {final}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={copiar}
          className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-semibold transition ${
            copiado
              ? "bg-emerald-500/15 text-emerald-500"
              : "bg-violet-500/15 text-violet-400 hover:bg-violet-500/25"
          }`}
        >
          {copiado ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copiado ? "Copiado" : "Copiar mensaje"}
        </button>
        <span className="text-[10px] text-muted-foreground">
          {final.length} caracteres
        </span>
        {editando && (
          <button
            type="button"
            onClick={onBorrar}
            className="ml-auto inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[11px] text-red-400 transition hover:border-red-500/50"
          >
            <Trash2 className="h-3 w-3" /> Borrar
          </button>
        )}
      </div>
    </section>
  );
}

/** Mensajes listos para copiar y pegar en el chat del vendedor.
 *
 *  No genera nada: son textos. Están aquí y no en cada nicho porque el mensaje
 *  habla de la CUENTA (nivel de creador, GMV), no del producto — y porque lo
 *  que se pide a un vendedor es lo mismo se grabe el nicho que se grabe.
 */
export default function PlantillasPage() {
  const { data, isLoading } = usePlantillas();
  const guardar = useGuardarPlantillas();
  const restaurar = useRestaurarPlantillas();

  // Copia local: se edita sin guardar en cada tecla y se manda entera al pulsar.
  const [items, setItems] = useState<Plantilla[]>([]);
  const [valores, setValores] = useState<Record<string, string>>({});
  const sucio = JSON.stringify(items) !== JSON.stringify(data ?? []);

  useEffect(() => {
    if (data) setItems(data);
  }, [data]);

  return (
    <div className="mx-auto max-w-3xl space-y-3 p-3 sm:p-4">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-lg font-semibold sm:text-xl">
          <MessageSquareText className="h-5 w-5 text-muted-foreground" /> Plantillas de mensajes
        </h1>
        <p className="text-[11px] text-muted-foreground sm:text-xs">
          Mensajes listos para copiar y pegar en el chat del vendedor. Pon tu @
          arriba y el texto sale montado. Escríbele DESDE la ficha del producto:
          así el chat ya dice de cuál hablas.
        </p>
      </header>

      {/* Los huecos, arriba del todo: se rellenan UNA vez y valen para todas
          las plantillas de la pantalla. */}
      <section className="grid grid-cols-1 gap-2 rounded-lg border border-border/60 bg-card p-3 sm:grid-cols-2">
        {HUECOS.map((h) => (
          <label key={h.clave} className="space-y-1">
            <span className="text-[11px] font-medium text-muted-foreground">{h.label}</span>
            <input
              value={valores[h.clave] ?? ""}
              onChange={(e) => setValores((p) => ({ ...p, [h.clave]: e.target.value }))}
              placeholder={h.ejemplo}
              className="w-full rounded-md border border-border/60 bg-background px-2 py-1.5 text-sm"
            />
          </label>
        ))}
      </section>

      {isLoading && <p className="text-xs text-muted-foreground">Cargando…</p>}

      {items.map((p, i) => (
        <TarjetaPlantilla
          key={p.id}
          plantilla={p}
          valores={valores}
          onCambiar={(nueva) =>
            setItems((prev) => prev.map((x, j) => (i === j ? nueva : x)))
          }
          onBorrar={() => setItems((prev) => prev.filter((_, j) => j !== i))}
        />
      ))}

      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={() =>
            setItems((prev) => [
              ...prev,
              {
                // El id solo tiene que ser único dentro de la lista; se usa de
                // `key` y para nada más.
                id: `plantilla-${prev.length + 1}-${Date.now()}`,
                titulo: "Mensaje nuevo",
                nota: "",
                texto: "",
              },
            ])
          }
          className="inline-flex items-center gap-1.5 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px] transition hover:border-foreground/40"
        >
          <Plus className="h-3.5 w-3.5" /> Añadir plantilla
        </button>
        <button
          type="button"
          disabled={!sucio || guardar.isPending}
          onClick={() =>
            guardar.mutate(items, {
              onSuccess: () => toast.success("Plantillas guardadas."),
              onError: (e) => toast.error(e.message),
            })
          }
          className="inline-flex items-center gap-1.5 rounded-md bg-violet-500/15 px-2.5 py-1.5 text-[11px] font-semibold text-violet-400 transition hover:bg-violet-500/25 disabled:opacity-40"
        >
          <Save className="h-3.5 w-3.5" />
          {guardar.isPending ? "Guardando…" : sucio ? "Guardar cambios" : "Guardado"}
        </button>
        <button
          type="button"
          disabled={restaurar.isPending}
          onClick={() => {
            if (!confirm("¿Descartar tus plantillas y volver a las de fábrica?")) return;
            restaurar.mutate(undefined, {
              onSuccess: () => toast.success("Plantillas restauradas."),
              onError: (e) => toast.error(e.message),
            });
          }}
          className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px] text-muted-foreground transition hover:border-foreground/40"
        >
          <RotateCcw className="h-3.5 w-3.5" /> Restaurar
        </button>
      </div>
    </div>
  );
}
