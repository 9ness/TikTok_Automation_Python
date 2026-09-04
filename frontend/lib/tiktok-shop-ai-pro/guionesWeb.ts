/** Los pegotes de consola que se usan en la web del curso.
 *
 *  Viven aquí y no dentro del panel que los enseña porque los usan dos sitios
 *  (las instrucciones por pasos y el cuadro de pegar las fichas) y porque cada
 *  uno costó descubrirlo: su web tiene trampas que no se ven leyendo el DOM.
 *
 *  `String.raw` a propósito: llevan expresiones regulares con barras
 *  invertidas (`\s`) que un template normal se comería.
 */

/** Su web usa JSZip para armar el ZIP en el navegador y NO lo carga: el botón
 *  de descargar carpeta revienta con "JSZip is not defined". Se carga a mano
 *  antes de tocar nada. */
export const GUION_JSZIP = String.raw`await new Promise((ok, ko) => {
  const s = document.createElement("script");
  s.src = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
  s.onload = ok; s.onerror = ko;
  document.head.appendChild(s);
});
console.log("JSZip:", typeof JSZip);   // tiene que decir "function"`;

/** Las carpetas se bajan pulsando su botón de descarga, con espera entre una y
 *  otra: el ZIP se arma en el navegador y encadenarlas se salta carpetas. */
export const GUION_ZIPS = String.raw`const btns = [...document.querySelectorAll("button[data-dl]")];
console.log("carpetas:", btns.length);
for (const b of btns) {
  const nombre = b.closest(".carp-head")?.querySelector("b")?.textContent.trim();
  b.click();
  console.log(b.dataset.dl, nombre, "→ descargando");
  await new Promise((r) => setTimeout(r, 15000));
}
console.log("FIN");`;

/** Las fichas de TikTok de cada producto, que en su web están al lado del
 *  número. Dos trampas suyas, las dos descubiertas a base de que no saliera:
 *   - Es un ACORDEÓN: al abrir una carpeta cierra la anterior, así que hay que
 *     leer cada una mientras está abierta, no desplegarlas todas.
 *   - Al abrir REPINTA la lista entera: el `div.carp` que tuvieras en la mano
 *     queda descolgado y su `.prod` no llega nunca. Por eso se vuelve a buscar
 *     por índice en cada vuelta.
 *  Y baja un fichero en vez de usar `copy()`: con `await`, Chrome envuelve el
 *  código y las utilidades de la consola dejan de existir. */
export const GUION_FICHAS = String.raw`const carps = () => [...document.querySelectorAll("div.carp")];
const filas = [];
for (let i = 0; i < carps().length; i++) {
  if (!carps()[i]?.querySelector(".prod")) {
    carps()[i]?.querySelector(".carp-head")?.click();
    for (let k = 0; k < 40 && !carps()[i]?.querySelector(".prod"); k++) {
      await new Promise((r) => setTimeout(r, 150));
    }
  }
  const c = carps()[i];
  if (!c) continue;
  const carpeta = c.querySelector(".carp-head b")?.textContent.trim();
  const antes = filas.length;
  c.querySelectorAll(".prod").forEach((p) => {
    filas.push({
      carpeta,
      producto: p.querySelector(".p-head b")?.textContent.trim(),
      url: p.querySelector("a.chip[href]")?.href ?? "",
      sin_stock: /sin\s*stock/i.test(p.textContent || ""),
    });
  });
  console.log(carpeta, "· en esta:", filas.length - antes, "· total:", filas.length);
}
const a = document.createElement("a");
a.href = URL.createObjectURL(new Blob([JSON.stringify(filas)]));
a.download = "fichas.json";
a.click();
console.log("TOTAL", filas.length, "·", filas.filter((f) => f.url).length, "con enlace ·", filas.filter((f) => f.sin_stock).length, "sin stock");`;
