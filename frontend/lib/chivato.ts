"use client";

import { api } from "@/lib/api";

/** Manda un dato suelto de depuración al servidor (`/diagnostics/cliente`).
 *
 *  Nunca lanza ni espera: si el chivato falla, la app sigue igual. El servidor
 *  se queda con 20 campos como mucho, así que no hace falta más.
 */
export function avisar(evento: Record<string, unknown>) {
  const key = process.env.NEXT_PUBLIC_API_KEY;
  try {
    void fetch(`${api.baseUrl}/api/v1/diagnostics/cliente`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(key ? { "X-API-Key": key } : {}) },
      body: JSON.stringify(evento),
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* depurar no puede romper nada */
  }
}

function caja(el: Element | null | undefined) {
  if (!el) return "";
  const r = el.getBoundingClientRect();
  return `${Math.round(r.width)}x${Math.round(r.height)}@${Math.round(r.left)},${Math.round(r.top)}`;
}

/** Mide la ventana emergente abierta y lo cuenta.
 *
 *  Existe porque el diálogo "a medias" solo pasa en el WebView del móvil: en
 *  Chrome de escritorio, y hasta con el mismo user-agent, se pinta entero. Sin
 *  poder mirar el DOM del móvil, la única forma de saber si la caja mide de
 *  menos (problema de medidas) o mide bien pero no se ve (problema de pintado)
 *  es que la propia app lo diga.
 */
export function medirDialogo(fase: string) {
  try {
    const d = document.querySelector<HTMLElement>('[role="dialog"][data-state="open"]');
    if (!d) return;
    const cs = getComputedStyle(d);
    avisar({
      tipo: "dialogo",
      fase,
      clases_html: document.documentElement.className.slice(0, 60),
      caja: caja(d),
      contenido: `${d.scrollHeight}px ${d.childElementCount}hijos`,
      primero: caja(d.firstElementChild),
      ultimo: caja(d.lastElementChild),
      css: `h=${cs.height} max=${cs.maxHeight} of=${cs.overflowY} op=${cs.opacity} vis=${cs.visibility} disp=${cs.display}`,
      transform: cs.transform.slice(0, 60),
      animacion: `${cs.animationName} ${cs.animationDuration}`,
      ventana: `${window.innerWidth}x${window.innerHeight} vv=${Math.round(
        window.visualViewport?.height ?? 0,
      )} doc=${document.documentElement.clientHeight} dpr=${window.devicePixelRatio}`,
      texto: (d.textContent || "").trim().slice(0, 50),
      ua: navigator.userAgent.slice(-45),
    });
  } catch {
    /* depurar no puede romper nada */
  }
}
