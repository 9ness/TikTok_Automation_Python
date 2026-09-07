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

/** Las carpetas se bajan pulsando su botón de descarga, esperando a que CADA
 *  ZIP salga de verdad antes de pedir el siguiente.
 *
 *  Antes se esperaba un tiempo fijo y no valía: el ZIP se arma en el navegador
 *  y tarda lo que tarda, así que unas carpetas se saltaban y a partir de la
 *  quincena larga dejaba de generarlos —el bucle seguía dando clics y no bajaba
 *  nada, sin un solo error—. Ahora:
 *
 *   - Se envuelve el `click()` del `<a download>` y `createObjectURL`, que es
 *     por donde su web suelta el fichero: eso avisa de que ESE ZIP ya está.
 *   - Se libera el blob unos segundos después (la descarga ya arrancó). Es lo
 *     que quita de encima la memoria acumulada, que es lo que la mataba.
 *   - Al terminar dice qué carpetas NO bajaron, listas para pegar en `QUIERO`.
 */
export const GUION_ZIPS = String.raw`const QUIERO = [];        // p. ej. [20,21,22]. Vacío = todas.
const LIMITE = 180000;    // por carpeta, antes de darla por perdida

let avisar = null;
const clickOrig = HTMLAnchorElement.prototype.click;
HTMLAnchorElement.prototype.click = function () {
  if (this.download || String(this.href || "").startsWith("blob:")) {
    avisar?.(this.download || this.href);
  }
  return clickOrig.apply(this, arguments);
};
const crearOrig = URL.createObjectURL.bind(URL);
URL.createObjectURL = (b) => {
  const u = crearOrig(b);
  avisar?.(u);
  setTimeout(() => URL.revokeObjectURL(u), 8000);
  return u;
};

const esperarZip = () => new Promise((ok) => {
  const t = setTimeout(() => { avisar = null; ok(null); }, LIMITE);
  avisar = (n) => {
    clearTimeout(t); avisar = null;
    setTimeout(() => ok(n), 1500);
  };
});

const btns = [...document.querySelectorAll("button[data-dl]")]
  .filter((b) => !QUIERO.length || QUIERO.includes(Number(b.dataset.dl)));
console.log("a bajar:", btns.length);
const faltan = [];
for (const b of btns) {
  b.scrollIntoView({ block: "center" });
  b.click();
  const listo = await esperarZip();
  if (listo) {
    console.log(b.dataset.dl, "OK");
  } else {
    faltan.push(Number(b.dataset.dl));
    console.warn(b.dataset.dl, "NO bajó");
  }
}
console.log("FIN · faltan:", JSON.stringify(faltan));`;

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
