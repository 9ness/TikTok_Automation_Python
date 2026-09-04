"use client";

import { Check, Copy, Download, Globe } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  GUION_FICHAS,
  GUION_JSZIP,
  GUION_ZIPS,
} from "@/lib/tiktok-shop-ai-pro/guionesWeb";

/** Cómo se baja de la web del curso lo que hace falta aquí: las fotos (ZIP) y
 *  las fichas de TikTok (JSON).
 *
 *  Está escrito como PASOS y no como un párrafo porque se hace de tarde en
 *  tarde —cada vez que publica un inventario nuevo— y entre una vez y otra no
 *  se recuerda ni el orden ni las dos trampas de su web (que hay que cargar
 *  JSZip a mano y que Chrome bloquea el primer pegado en la consola). Cada
 *  paso trae su botón: lo que se copia no se teclea mal.
 */
export function PanelWebCurso() {
  return (
    <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
      <div className="flex items-center gap-2">
        <Globe className="h-4 w-4 shrink-0 text-sky-500" />
        <p className="text-sm font-semibold">Traer de la web del curso</p>
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Todo esto se hace en <code>ttshopaiproapp.com</code>, en la página del
        listado de carpetas. Abre las herramientas con{" "}
        <strong className="text-foreground">F12 → Console</strong>. La primera
        vez Chrome no deja pegar: escribe a mano{" "}
        <code>allow pasting</code>, Enter, y ya te deja (solo una vez por
        perfil).
      </p>

      <Bloque
        icono={<Download className="h-3.5 w-3.5" />}
        titulo="A · Las fotos (los ZIP)"
        color="violeta"
        pasos={[
          {
            texto:
              "Carga JSZip. Su web lo usa para armar el ZIP y no lo carga: sin esto el botón de descargar carpeta falla con «JSZip is not defined». Tiene que responder «function».",
            guion: GUION_JSZIP,
            etiqueta: "Copiar paso 1",
          },
          {
            texto:
              "Baja todas las carpetas, una cada 15 s. Chrome preguntará si permites descargar varios archivos: dile que sí. Al acabar comprueba que hay tantos ZIP como carpetas te haya dicho el log.",
            guion: GUION_ZIPS,
            etiqueta: "Copiar paso 2",
          },
        ]}
        pie="Los ZIP bajan como Carpeta_N.zip, que es el nombre que espera el importador. Se suben en la pantalla del nicho que toque (POV BOF · Productos Web, o Ropa Mujer/Hombre eligiendo antes de quién son)."
      />

      <Bloque
        icono={<Copy className="h-3.5 w-3.5" />}
        titulo="B · Las fichas de TikTok (el JSON)"
        color="esmeralda"
        pasos={[
          {
            texto:
              "Saca el enlace de la ficha de cada producto. Va carpeta por carpeta (su web cierra una al abrir la siguiente) y al terminar te descarga fichas.json.",
            guion: GUION_FICHAS,
            etiqueta: "Copiar el guion",
          },
        ]}
        pie="Ese fichero se pega aquí abajo, en «Fichas de TikTok Shop», con el catálogo correcto elegido. Cada enlace vale para todas las carpetas de ese producto, para todos los nichos y para las tres cuentas: sacarlo con EchoTik cuesta una llamada por producto."
      />
    </section>
  );
}

const COLORES = {
  violeta: "border-violet-500/40 bg-violet-500/5 text-violet-400",
  esmeralda: "border-emerald-500/40 bg-emerald-500/5 text-emerald-500",
} as const;

function Bloque({
  icono,
  titulo,
  color,
  pasos,
  pie,
}: {
  icono: React.ReactNode;
  titulo: string;
  color: keyof typeof COLORES;
  pasos: { texto: string; guion: string; etiqueta: string }[];
  pie: string;
}) {
  return (
    <div className={`space-y-2 rounded-lg border p-2.5 ${COLORES[color]}`}>
      <p className="flex items-center gap-1.5 text-[11px] font-semibold sm:text-xs">
        {icono} {titulo}
      </p>
      <ol className="space-y-2">
        {pasos.map((p, i) => (
          <li key={p.etiqueta} className="flex gap-2">
            <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-background text-[9px] font-bold text-foreground">
              {i + 1}
            </span>
            <div className="min-w-0 flex-1 space-y-1.5">
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                {p.texto}
              </p>
              <BotonCopiar etiqueta={p.etiqueta} guion={p.guion} />
            </div>
          </li>
        ))}
      </ol>
      <p className="text-[10px] leading-relaxed text-muted-foreground">{pie}</p>
    </div>
  );
}

/** Copia y se queda marcado unos segundos.
 *
 *  El aviso solo no basta: con dos guiones seguidos, sin ver cuál se copió es
 *  fácil pegar dos veces el mismo y quedarse mirando por qué no baja nada. */
function BotonCopiar({ etiqueta, guion }: { etiqueta: string; guion: string }) {
  const [copiado, setCopiado] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(guion);
        setCopiado(true);
        toast.success(`${etiqueta.replace("Copiar ", "")} copiado`);
        setTimeout(() => setCopiado(false), 4000);
      }}
      className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 bg-background px-2 py-1.5 text-[11px] font-medium text-foreground transition hover:border-foreground/30 sm:w-auto sm:px-3"
    >
      {copiado ? (
        <>
          <Check className="h-3.5 w-3.5 text-emerald-500" /> Copiado
        </>
      ) : (
        <>
          <Copy className="h-3.5 w-3.5" /> {etiqueta}
        </>
      )}
    </button>
  );
}
