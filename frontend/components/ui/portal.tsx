"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

/** Cuelga lo que envuelve del `<body>`, fuera de donde se usa.
 *
 *  Hace falta para CUALQUIER ventana `position: fixed`. Esa posición deja de
 *  referirse a la pantalla en cuanto un ancestro tiene `transform`, `filter` o
 *  `contain`, y entonces la ventana se recorta a ese ancestro — o directamente
 *  no se ve. En el móvil pasó dos veces: el visor de fotos salía como una tira
 *  con el título cortado, y el reproductor de la cola no llegaba a abrirse
 *  porque vive DENTRO del cajón de la cola.
 *
 *  Va aparte y no copiado en cada modal a propósito: es la tercera vez que el
 *  mismo fallo aparece en un sitio distinto.
 */
export function Portal({ children }: { children: React.ReactNode }) {
  // El primer render tiene que coincidir con el del servidor, donde no hay
  // `document`. Se monta después.
  const [listo, setListo] = useState(false);
  useEffect(() => setListo(true), []);
  if (!listo || typeof document === "undefined") return null;
  return createPortal(children, document.body);
}
