"use client";

import { Clock } from "lucide-react";

/** Cuándo se terminó de montar el vídeo, debajo del botón de descargar.
 *
 *  Para qué: una carpeta se trabaja en varias sesiones y el botón de descargar
 *  tiene el mismo aspecto para un vídeo de hace diez minutos que para uno de
 *  hace cinco días. Sin la fecha no hay forma de saber si eso ya se subió.
 *
 *  Va DEBAJO y no dentro del botón: en un móvil estrecho la etiqueta se partía
 *  en tres renglones y el botón crecía el doble que el de al lado.
 *
 *  Lo de hoy sale en gris y lo de días anteriores en ÁMBAR: lo que se busca de
 *  un vistazo no es la fecha, es "esto no es de ahora".
 */
export function MontadoEl({ ts }: { ts?: number | null }) {
  if (!ts) return null;
  const cuando = new Date(ts * 1000);
  if (Number.isNaN(cuando.getTime())) return null;

  const hoy = new Date();
  const dia = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  const esHoy = dia(cuando) === dia(hoy);
  const ayer = new Date(hoy);
  ayer.setDate(hoy.getDate() - 1);
  const esAyer = dia(cuando) === dia(ayer);

  const hora = cuando.toLocaleTimeString("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const fecha = cuando.toLocaleDateString("es-ES", {
    day: "numeric",
    month: "short",
  });
  const texto = esHoy
    ? `hoy ${hora}`
    : esAyer
      ? `ayer ${hora}`
      : `${fecha} · ${hora}`;

  return (
    <p
      className={`flex items-center justify-center gap-1 pt-0.5 text-[10px] leading-tight ${
        esHoy ? "text-muted-foreground" : "text-amber-500"
      }`}
      title={`Vídeo montado el ${cuando.toLocaleString("es-ES")}`}
    >
      <Clock className="h-3 w-3 shrink-0" strokeWidth={2} />
      Montado {texto}
    </p>
  );
}
