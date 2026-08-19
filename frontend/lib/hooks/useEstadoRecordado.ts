"use client";

import { useEffect, useRef, useState } from "react";

import { ultimoUsuario } from "@/lib/cache-persistente";
import { useMe } from "@/lib/queries/auth";

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
  // El valor por defecto de la PRIMERA vez: si el caller lo recrea en cada
  // render (un objeto literal), volver a él no debe depender de esa identidad.
  const inicialRef = useRef(inicial);

  useEffect(() => {
    try {
      const guardado = localStorage.getItem(clave);
      // Si la clave CAMBIA y ahí no hay nada, se vuelve al valor por defecto en
      // vez de quedarse con lo de la clave anterior. Importa con las claves por
      // usuario (`useEstadoDeUsuario`): sin esto, al pasar a la cuenta de Ana
      // se quedaba abierta la carpeta que estaba mirando yo.
      setValor(guardado !== null ? (JSON.parse(guardado) as T) : inicialRef.current);
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


/** Como `useEstadoRecordado` pero la clave lleva el usuario dentro.
 *
 *  Para lo que es "por dónde iba": la fuente y la carpeta abiertas. Sin esto,
 *  al cambiar de cuenta te quedabas en la carpeta que estabas mirando tú y no
 *  en la que lleva la otra persona — cosmético, pero despista al entrar a
 *  ayudarles. (Es local a cada dispositivo: nunca viajó a su móvil.)
 *
 *  El usuario se saca de `/me`, y mientras contesta se usa el último que entró
 *  (lo deja escrito el propio cambio de cuenta, ver `cache-persistente`), así
 *  que en la práctica la clave ya es la buena en el primer render. Si acaba
 *  siendo otro, la clave cambia y `useEstadoRecordado` recarga lo suyo.
 */
export function useEstadoDeUsuario<T>(
  clave: string,
  inicial: T,
): [T, (v: T | ((prev: T) => T)) => void] {
  const deLaSesion = useMe().data?.username;
  const [ultimo] = useState(() =>
    typeof window === "undefined" ? "" : ultimoUsuario(),
  );
  const quien = deLaSesion || ultimo || "?";
  return useEstadoRecordado(`u:${quien}:${clave}`, inicial);
}
