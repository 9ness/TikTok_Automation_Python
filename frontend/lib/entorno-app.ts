/** ¿Estamos dentro de la app de Android, y de cuál?
 *
 *  Vive aquí porque la respuesta ya se necesitaba en dos sitios y en los dos
 *  estaba mal por el mismo motivo: se miraba `display-mode: standalone` y el
 *  referrer `android-app://`, que valían para la TWA pero NO para la APK nueva,
 *  que es un WebView y no cumple ninguna de las dos. Primero dejó de salir el
 *  aviso de actualizar; después dejó de restaurarse la última pantalla.
 *
 *  Lo único fiable en la app nueva es la marca del User-Agent, que le pone
 *  `MainActivity` al arrancar.
 */

/** La APK nueva (WebView propio). */
export function enLaApp(): boolean {
  if (typeof navigator === "undefined") return false;
  return /TTShopApp/.test(navigator.userAgent);
}

/** Cualquier cosa que no sea una pestaña suelta del navegador: la APK nueva,
 *  la TWA vieja o el icono de la pantalla de inicio. Es lo que importa cuando
 *  la pregunta es "¿puede Android matarme la tarea y devolverme al principio?".
 *
 *  Ojo con el referrer: la TWA solo lo pone en la navegación de ARRANQUE, así
 *  que en cuanto se navega desaparece. Por eso nunca puede ser la única señal.
 */
export function enAlgunaApp(): boolean {
  if (typeof window === "undefined") return false;
  return (
    enLaApp() ||
    window.matchMedia("(display-mode: standalone)").matches ||
    document.referrer.startsWith("android-app://") ||
    // iOS lo expone aquí; se mira igualmente por si se añade soporte.
    (window.navigator as { standalone?: boolean }).standalone === true
  );
}
