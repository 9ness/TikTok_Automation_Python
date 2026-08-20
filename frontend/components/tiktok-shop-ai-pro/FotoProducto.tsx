"use client";

import { useEffect, useState } from "react";

/** La miniatura de un producto, con reintento.
 *
 *  Una foto rota no es un fallo del fichero: casi siempre es la API ocupada
 *  (un trabajo pesado en la cola, el Drive tardando) devolviendo 502 para esa
 *  imagen suelta. El navegador no reintenta solo, así que la tarjeta se quedaba
 *  con el icono roto hasta recargar la página entera.
 *
 *  Aquí se reintenta dos veces con un poco de espera y, si aun así no viene, se
 *  dice —en vez de dejar el icono roto, que no explica nada.
 */
export function FotoProducto({
  src,
  alt,
  className = "",
  claseHueco = "",
  onClick,
}: {
  src: string | null;
  alt: string;
  className?: string;
  /** Clases para el hueco de "no cargó". Hace falta donde la foto es lo único
   *  que da altura —el visor a pantalla completa—: sin un alto mínimo, el
   *  aviso sale aplastado y parece que no ha pasado nada. */
  claseHueco?: string;
  onClick?: () => void;
}) {
  const [intento, setIntento] = useState(0);
  const [fallo, setFallo] = useState(false);

  // Al cambiar de carpeta la tarjeta se reutiliza (los productos se numeran
  // 1..10 en todas): sin esto se quedaría en "no cargó" para la foto nueva.
  useEffect(() => {
    setIntento(0);
    setFallo(false);
  }, [src]);

  if (!src || fallo) {
    return (
      <div
        className={`flex items-center justify-center bg-muted text-center text-[9px] leading-tight text-muted-foreground ${className} ${claseHueco}`}
      >
        {src ? "no cargó" : ""}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      // El contador va en la URL a propósito: sin cambiarla, el navegador
      // sirve el fallo cacheado y el reintento no llega a pedir nada.
      src={intento ? `${src}&reintento=${intento}` : src}
      alt={alt}
      loading="lazy"
      onClick={onClick}
      onError={() => {
        if (intento >= 2) {
          setFallo(true);
          return;
        }
        setTimeout(() => setIntento((n) => n + 1), 800 * (intento + 1));
      }}
      className={className}
    />
  );
}
