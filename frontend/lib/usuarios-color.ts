/** Un color por persona, el MISMO en toda la app.
 *
 *  Para qué: con la cola compartida entre tres cuentas, "de quién es esto" hay
 *  que verlo de un vistazo — en la tarjeta del trabajo y en el contador de la
 *  cabecera. Un nombre escrito se lee; un color se reconoce sin leer.
 *
 *  El de `ness` es rojo porque es el que ya tenía el contador de la cabecera.
 *  Los demás se reparten para que se distingan entre sí también en oscuro.
 */
export interface ColorUsuario {
  /** Fondo del circulito/píldora. */
  punto: string;
  /** Píldora con nombre: borde + fondo tenue + texto. */
  pildora: string;
  /** Solo el texto, para cuando ya hay fondo. */
  texto: string;
}

const COLORES: Record<string, ColorUsuario> = {
  ness: {
    punto: "bg-red-500",
    pildora: "border-red-500/40 bg-red-500/15 text-red-600 dark:text-red-300",
    texto: "text-red-600 dark:text-red-300",
  },
  ana: {
    punto: "bg-amber-500",
    pildora: "border-amber-500/40 bg-amber-500/15 text-amber-600 dark:text-amber-300",
    texto: "text-amber-600 dark:text-amber-300",
  },
  mauro: {
    punto: "bg-violet-500",
    pildora: "border-violet-500/40 bg-violet-500/15 text-violet-600 dark:text-violet-300",
    texto: "text-violet-600 dark:text-violet-300",
  },
};

/** Para quien no esté en la lista (usuario nuevo, o los jobs viejos sin dueño):
 *  gris, que no compite con los tres de arriba. */
const NEUTRO: ColorUsuario = {
  punto: "bg-slate-400",
  pildora: "border-slate-400/40 bg-slate-400/15 text-slate-600 dark:text-slate-300",
  texto: "text-slate-600 dark:text-slate-300",
};

export function colorDeUsuario(usuario: string | null | undefined): ColorUsuario {
  return COLORES[(usuario || "").trim().toLowerCase()] ?? NEUTRO;
}

/** Nombre para enseñar. Los jobs de antes del multiusuario no tienen dueño
 *  guardado: son del administrador, que era el único que había. */
export function nombreDueno(usuario: string | null | undefined): string {
  const u = (usuario || "").trim();
  if (!u || u === "api-key-user" || u === "anonymous" || u === "None") return "ness";
  return u;
}
