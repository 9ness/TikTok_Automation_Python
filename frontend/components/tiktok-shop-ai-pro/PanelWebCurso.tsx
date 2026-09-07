"use client";

import { Check, Copy, Download, Globe, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useEstadoDeUsuario } from "@/lib/hooks/useEstadoRecordado";
import {
  GUION_FICHAS,
  GUION_JSZIP,
  GUION_ZIPS,
} from "@/lib/tiktok-shop-ai-pro/guionesWeb";
import { ImportarPrendasWeb } from "@/components/tiktok-shop-ai-pro/ImportarPrendasWeb";
import { ImportarZipWeb } from "@/components/tiktok-shop-ai-pro/ImportarZipWeb";
import { PegarFichasCatalogo } from "@/components/tiktok-shop-ai-pro/PegarFichasCatalogo";
import { PegarFichasRopa } from "@/components/tiktok-shop-ai-pro/PegarFichasRopa";

/** Traerse de la web del curso un catálogo entero: las fotos (ZIP) y las
 *  fichas de TikTok (JSON), de principio a fin y sin salir de aquí.
 *
 *  Antes esto solo explicaba cómo BAJARLO y luego había que irse a la pantalla
 *  del nicho a subirlo — y el Inventario General alimenta a varios, así que
 *  ninguna pantalla era "la suya". Ahora se elige el catálogo arriba y los
 *  cuatro pasos van en orden: bajar ZIP, subir ZIP, bajar fichas, subir fichas.
 *
 *  Está escrito como PASOS y no como un párrafo porque se hace de tarde en
 *  tarde —cada vez que publica un inventario nuevo— y entre una vez y otra no
 *  se recuerda ni el orden ni las trampas de su web (hay que cargar JSZip a
 *  mano, Chrome bloquea el primer pegado en la consola y en móvil ya no arma
 *  el ZIP). Cada paso trae su botón: lo que se copia no se teclea mal.
 */
const CATALOGOS = [
  {
    clave: "inventario_general",
    label: "📦 Inventario General",
    // De dónde se bajan las cosas en su web, para no tener que adivinarlo.
    donde: "Productos de España › Inventario General",
  },
  // "Moda Hombre" y "Moda Mujer" son TRES inventarios cada uno en su web
  // (Ropa / Zapatos / Accesorios) y hoy solo hay productos en Ropa. Cuando
  // llenen los otros dos habrá que darlos de alta aquí: no son la misma
  // carpeta ni sirven para los mismos formatos —los zapatos van al POV BOF
  // Largo y las gafas al modo del coche—.
  { clave: "hombre_web", label: "👔 Ropa Hombre", donde: "Moda Hombre › Ropa Hombre" },
  { clave: "mujer_web", label: "👗 Ropa Mujer", donde: "Moda Mujer › Ropa Mujer" },
] as const;

type ClaveCatalogo = (typeof CATALOGOS)[number]["clave"];

export function PanelWebCurso() {
  const [catalogo, setCatalogo] = useEstadoDeUsuario<ClaveCatalogo>(
    "web-curso:catalogo",
    "inventario_general",
  );
  const elegido = CATALOGOS.find((c) => c.clave === catalogo) ?? CATALOGOS[0];
  const esRopa = elegido.clave !== "inventario_general";

  return (
    <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
      <div className="flex items-center gap-2">
        <Globe className="h-4 w-4 shrink-0 text-sky-500" />
        <p className="text-sm font-semibold">Traer de la web del curso</p>
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Lo de bajar se hace en <code>ttshopaiproapp.com</code>, en la página que
        diga cada paso, con{" "}
        <strong className="text-foreground">F12 → Console</strong>. La primera
        vez Chrome no deja pegar: escribe a mano <code>allow pasting</code>,
        Enter, y ya te deja (solo una vez por perfil).
      </p>

      {/* El catálogo manda en TODO: de qué página se baja y a qué inventario
          entra. Se elige una vez arriba en vez de repetirlo en cada paso. */}
      <div className="space-y-1">
        <p className="text-[11px] font-semibold">¿Qué catálogo?</p>
        <div className="grid grid-cols-3 gap-1.5">
          {CATALOGOS.map((c) => (
            <button
              key={c.clave}
              type="button"
              onClick={() => setCatalogo(c.clave)}
              className={`break-words rounded-lg border px-2 py-1.5 text-[11px] leading-tight transition ${
                catalogo === c.clave
                  ? "border-sky-500 bg-sky-500/10 font-semibold text-sky-400"
                  : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-muted-foreground">
          En su web: <strong className="text-foreground">{elegido.donde}</strong>
        </p>
      </div>

      <Bloque
        icono={<Download className="h-3.5 w-3.5" />}
        titulo="1 · Bajar las fotos (los ZIP)"
        color="violeta"
        pasos={[
          {
            texto:
              "Desde un PC y SIN la vista móvil de DevTools (Ctrl+Shift+M la apaga). Desde sep 2026 su web detecta el móvil y ahí ya NO arma ZIP: abre un panel para guardar las fotos sueltas, así que el bucle da los clics y no baja nada.",
          },
          {
            texto:
              "Carga JSZip. Su web lo usa para armar el ZIP y no lo carga: sin esto el botón de descargar carpeta falla con «JSZip is not defined». Tiene que responder «function».",
            guion: GUION_JSZIP,
            etiqueta: "Copiar paso 1",
          },
          {
            texto:
              "Baja las carpetas, esperando a que cada ZIP salga de verdad antes de pedir el siguiente. La primera vez Chrome bloquea las descargas múltiples: en el icono a la izquierda de la URL → Configuración del sitio → Descargas automáticas → Permitir. Al terminar dice «faltan: [...]»: si sale alguna, recarga la página, vuelve a cargar JSZip y relanza pegando esos números en QUIERO.",
            guion: GUION_ZIPS,
            etiqueta: "Copiar paso 2",
          },
        ]}
        pie="Los ZIP bajan como Carpeta_N.zip, que es el nombre que espera el importador."
      />

      <div className="space-y-2 rounded-lg border border-cyan-500/40 bg-cyan-500/5 p-2.5">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold text-cyan-400 sm:text-xs">
          <Upload className="h-3.5 w-3.5" /> 2 · Subir los ZIP a {elegido.label}
        </p>
        {esRopa ? (
          <ImportarPrendasWeb genero={elegido.clave} onImportado={() => {}} />
        ) : (
          <ImportarZipWeb source={elegido.clave} onImportado={() => {}} />
        )}
      </div>

      <Bloque
        icono={<Copy className="h-3.5 w-3.5" />}
        titulo="3 · Bajar las fichas de TikTok (el JSON)"
        color="esmeralda"
        pasos={[
          {
            texto:
              "En la MISMA página de la que bajaste los ZIP. Saca el enlace de la ficha de cada producto: va carpeta por carpeta (su web cierra una al abrir la siguiente) y al terminar te descarga fichas.json.",
            guion: GUION_FICHAS,
            etiqueta: "Copiar el guion",
          },
        ]}
        pie="Cada enlace vale para todas las carpetas de ese producto, para todos los nichos y para las tres cuentas: sacarlo con EchoTik cuesta una llamada por producto y el plan gratis son 100 al mes."
      />

      <div className="space-y-2 rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-2.5">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-500 sm:text-xs">
          <Copy className="h-3.5 w-3.5" /> 4 · Subir el fichas.json de{" "}
          {elegido.label}
        </p>
        {esRopa ? (
          <PegarFichasRopa genero={elegido.clave} />
        ) : (
          <PegarFichasCatalogo source={elegido.clave} />
        )}
      </div>
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
  // Sin `guion` es un paso que se hace a mano y no tiene nada que copiar
  // (apagar la vista móvil, por ejemplo).
  pasos: { texto: string; guion?: string; etiqueta?: string }[];
  pie: string;
}) {
  return (
    <div className={`space-y-2 rounded-lg border p-2.5 ${COLORES[color]}`}>
      <p className="flex items-center gap-1.5 text-[11px] font-semibold sm:text-xs">
        {icono} {titulo}
      </p>
      <ol className="space-y-2">
        {pasos.map((p, i) => (
          <li key={p.etiqueta ?? i} className="flex gap-2">
            <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-background text-[9px] font-bold text-foreground">
              {i + 1}
            </span>
            <div className="min-w-0 flex-1 space-y-1.5">
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                {p.texto}
              </p>
              {p.guion && p.etiqueta ? (
                <BotonCopiar etiqueta={p.etiqueta} guion={p.guion} />
              ) : null}
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
