"use client";

import { useEffect, useRef, useState } from "react";

/** `useState` que sobrevive a que Android mate la app.
 *
 *  Android reinicia la tarea al minuto de dejarla de fondo y eso no se puede
 *  evitar desde la web. `RestaurarPantalla` ya devuelve a la PANTALLA, pero la
 *  fuente y la carpeta abiertas viven en el estado del componente, así que al
 *  volver aparecías en la carpeta por defecto y había que buscar otra vez por
 *  dónde ibas — que es donde de verdad se pierde el tiempo cuando estás
 *  copiando guiones producto a producto.
 *
 *  Se guarda en `localStorage` en cuanto cambia, no al salir: cuando el sistema
 *  mata el proceso no llega ningún evento de despedida.
 *
 *  El valor inicial es SIEMPRE el que se pasa; lo guardado se aplica en el
 *  primer efecto. Es a propósito: leer `localStorage` durante el render
 *  rompería la hidratación de Next (el servidor no lo tiene).
 */
export function useEstadoRecordado<T>(
  clave: string,
  inicial: T,
): [T, (v: T | ((prev: T) => T)) => void] {
  const [valor, setValor] = useState<T>(inicial);
  const leido = useRef(false);

  useEffect(() => {
    try {
      const guardado = localStorage.getItem(clave);
      if (guardado !== null) setValor(JSON.parse(guardado) as T);
    } catch {
      /* localStorage lleno o JSON corrupto: se sigue con el valor inicial. */
    }
    leido.current = true;
  }, [clave]);

  useEffect(() => {
    // Sin esta guarda, el primer render pisaría lo guardado con el valor por
    // defecto justo antes de leerlo.
    if (!leido.current) return;
    try {
      localStorage.setItem(clave, JSON.stringify(valor));
    } catch {
      /* idem */
    }
  }, [clave, valor]);

  return [valor, setValor];
}
