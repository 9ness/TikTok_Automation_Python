"use client";

import { Loader2, RotateCw, Sparkles, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { escucharAvisos, lanzarEnSegundoPlano, soportaBgFetch, tandaEnMarcha } from "@/lib/bgFetch";
import {
  alSubirCadaFichero,
  alTerminarLaApp,
  haySubidaNativa,
  subirConLaApp,
} from "@/lib/subidaNativa";
import { useEstadoRecordado } from "@/lib/hooks/useEstadoRecordado";
import {
  actualizarLote,
  borrarLote,
  crearLote,
  ficherosDe,
  guardarReparto,
  idDeLote,
  leerLote,
  marcarToken,
} from "@/lib/loteIdb";
import {
  archivoLoteUrl,
  baseApi,
  claveApi,
  subirUno,
  urlSubidaLote,
  useConfirmarLote,
  useRepartirLote,
  type LoteItem,
} from "@/lib/queries/nichoPovBof";
import { buildPhotoUrl } from "@/lib/queries/nichoPovBof";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

type Sexo = "auto" | "hombre" | "mujer";

type FichaMinima = Pick<
  ProductoItem, "producto" | "titulo" | "clean_photo_id" | "modo_plazos" | "clip1" | "clip2"
> & {
  /** Solo el POV BOF Largo: los guiones que pasan de 25s piden TRES clips. */
  clips_necesarios?: number;
  clip3?: boolean;
  clip4?: boolean;
};

/** Una fila del repaso, ya colocada: qué vídeo es, de qué producto y si es el
 *  clip 1 o el 2. `idx` es la posición REAL en el reparto — el orden de la
 *  pantalla cambia, el del estado no. */
interface Fila {
  it: LoteItem;
  idx: number;
  ficha?: FichaMinima;
  doble: boolean;
  /** 1..N en los productos de varios clips; 0 en los de uno solo. */
  clip: number;
  /** Cuántos pide ese producto (2 normalmente, 3 con guion largo). */
  cuantos: number;
  /** Producto de dos clips al que le falta el otro: así NO se encola. */
  falta: boolean;
  /** Primero de su grupo: solo ahí se pinta la cabecera del producto. */
  abreGrupo: boolean;
}

/** Ordena el repaso por producto para poder repasarlo de un tirón.
 *
 *  Los dos vídeos de un mismo producto salían separados y había que ir y venir
 *  para comprobar que la pareja estaba bien. Aquí van juntos y numerados, y lo
 *  que no reconoció queda al final, que es lo único que hay que tocar a mano.
 */
function ordenarPorProducto(
  reparto: LoteItem[], productos: FichaMinima[], todosDobles: boolean,
): Fila[] {
  const ficha = new Map(productos.map((p) => [p.producto, p]));
  const esDoble = (p?: FichaMinima) => Boolean(p && (todosDobles || p.modo_plazos));
  // Cuántos clips pide el producto: los guiones largos del Largo piden tres.
  // Entre dos y cuatro: es lo que puede pedir `config.clips_necesarios` con
  // los clips de 8s, y más huecos de los que hay en la ficha dejarían al
  // producto esperando un clip que no se puede subir.
  const cuantosDe = (p?: FichaMinima) =>
    Math.min(4, Math.max(2, Number(p?.clips_necesarios) || 2));

  const grupos = new Map<string, { it: LoteItem; idx: number }[]>();
  reparto.forEach((it, idx) => {
    const clave = it.producto || "";
    const lista = grupos.get(clave) ?? [];
    lista.push({ it, idx });
    grupos.set(clave, lista);
  });

  const claves = [...grupos.keys()]
    .filter((k) => k)
    .sort((a, b) => {
      const na = Number(a);
      const nb = Number(b);
      return Number.isNaN(na) || Number.isNaN(nb) ? a.localeCompare(b) : na - nb;
    });
  // Los sin asignar, al final: son los que piden trabajo.
  if (grupos.has("")) claves.push("");

  const filas: Fila[] = [];
  for (const clave of claves) {
    const grupo = grupos.get(clave) ?? [];
    const p = ficha.get(clave);
    const doble = Boolean(clave) && esDoble(p);
    const cuantos = doble ? cuantosDe(p) : 0;
    const yaPuestos = [p?.clip1, p?.clip2, p?.clip3, p?.clip4].filter(Boolean).length;
    grupo.forEach(({ it, idx }, n) => {
      // Con varios vídeos en la tanda, el enésimo es su clip n. Con uno solo,
      // va al primer hueco libre (mismo criterio que el backend).
      const clip = !doble ? 0 : grupo.length >= 2 ? n + 1 : yaPuestos + 1;
      filas.push({
        it, idx, ficha: p, doble, clip, cuantos,
        falta: doble && grupo.length + yaPuestos < cuantos,
        abreGrupo: n === 0,
      });
    });
  }
  return filas;
}

/** Subir los vídeos de una carpeta de golpe y que cada uno vaya a su producto.
 *
 *  El vídeo se genera fuera (Magnific, Veo3, Kling) y vuelve con un nombre que
 *  no dice nada, así que había que subirlos de uno en uno a su ficha. Aquí se
 *  sueltan todos, la IA los reparte mirando los fotogramas y el operador solo
 *  repasa.
 *
 *  Lo importante del repaso: la IA acierta de sobra con productos distintos,
 *  pero con colchones o sofás gemelos se equivoca, y cuando se equivoca lo hace
 *  con total seguridad. Por eso el repaso existe — pero es OPCIONAL: con el
 *  check quitado se reparte y se encola sin preguntar, que es lo que se quiere
 *  en carpetas de productos claramente distintos.
 *
 *  La tanda NO vive solo en esta pantalla: los ficheros y los tokens se guardan
 *  en IndexedDB (`lib/loteIdb.ts`) y, donde se puede, la subida corre en
 *  segundo plano (`lib/bgFetch.ts`). Cerrar la app o que Android la mate ya no
 *  obliga a volver a subir 30 MB por vídeo.
 */
export function SubidaMasiva({
  source,
  folder,
  productos,
  root = "/api/v1/nicho-pov-bof",
  todosDobles = false,
  sinMarco = false,
}: {
  source: string;
  folder: string;
  /** Sirve igual la ficha del POV BOF que la del Largo: se usan el número, el
   *  título, la foto y si el producto va de plazos (dos clips). */
  productos: Pick<
    ProductoItem, "producto" | "titulo" | "clean_photo_id" | "modo_plazos" | "clip1" | "clip2"
  >[];
  /** Raíz de la API del nicho. En el Largo cada producto lleva dos clips y de
   *  eso se encarga su endpoint, no esta pantalla. */
  root?: string;
  /** En el POV BOF Largo TODOS los productos van en dos clips, no solo los de
   *  plazos. Cambia lo que se enseña al repasar (Clip 1 / Clip 2). */
  todosDobles?: boolean;
  /** Sin su propio recuadro: cuando va DENTRO de un paso, que ya lo tiene. */
  sinMarco?: boolean;
}) {
  const repartir = useRepartirLote(root);
  const confirmar = useConfirmarLote(root);
  // Por dónde va la subida: qué fichero y su porcentaje.
  const [progreso, setProgreso] = useState<{ n: number; total: number; pct: number } | null>(null);
  const [reconociendo, setReconociendo] = useState(false);
  // Las fotos de producto salen del nicho del POV BOF también en el Largo:
  // las carpetas son las mismas.
  const fotoUrl = (s: string, f: string, id: string) => buildPhotoUrl(s, f, id, 160);
  const [abierto, setAbierto] = useState(false);
  const [reparto, setReparto] = useState<LoteItem[] | null>(null);
  const [sexo, setSexo] = useEstadoRecordado<Sexo>("lote:sexo", "auto");
  /** Marcado = repasar antes de editar (lo de siempre). Sin marcar = directo. */
  const [confirmarAntes, setConfirmarAntes] = useEstadoRecordado("lote:confirmar", true);
  /** Tanda a medias encontrada al abrir la pantalla. */
  const [pendiente, setPendiente] = useState<{ subidos: number; total: number } | null>(null);
  /** La subida va por su cuenta en el sistema: no hay que dejar la app abierta. */
  const [enSegundoPlano, setEnSegundoPlano] = useState(false);
  /** Lo que se acaba de elegir en el selector, aún sin mandar. */
  const [elegidos, setElegidos] = useState<File[]>([]);
  /** Lo que quedó sin encolar y por qué. En pantalla hasta que se cierre: en
   *  un toast se pierde y luego no cuadra la cuenta de la cola. */
  const [avisos, setAvisos] = useState<string[]>([]);

  const loteId = idDeLote(root, source, folder);
  const cancelar = useRef<AbortController | null>(null);

  const conFoto = productos.filter((p) => p.clean_photo_id);
  const subiendo = Boolean(progreso) || reconociendo || enSegundoPlano;

  /** Manda a editar sin repaso y devuelve lo que NO se encoló.
   *
   *  Los que no reconoció no se tiran: se devuelven para que el operador los
   *  asigne. Montar un vídeo en el producto equivocado es peor que dejarlo
   *  esperando, pero descartarlo en silencio es lo peor de todo — pasó con una
   *  tanda de 5 en la que solo se editaron 4.
   */
  const encolarDirecto = useCallback(
    async (items: LoteItem[], vozElegida: Sexo) => {
      const listos = items.filter((i) => i.producto);
      const sinAsignar = items.filter((i) => !i.producto);
      if (!listos.length) {
        toast.warning("No reconoció ningún vídeo: asígnalos tú.");
        return { encolados: 0, sinAsignar, avisos: [] as string[] };
      }
      const r = await confirmar.mutateAsync({
        source,
        folder,
        items: listos.map((i) => ({ token: i.token, producto: i.producto })),
        sexo: vozElegida,
        con_gancho: true,
        con_titulo: true,
        con_cta: true,
        con_flecha: true,
      });
      toast.success(`${r.encolados} vídeo(s) en la cola, editando…`);
      // Lo que el backend NO encoló (productos de plazos a los que les falta
      // el otro clip, sobre todo) se queda escrito en pantalla: en un toast se
      // pierde y la cuenta de la cola no cuadra sin saber por qué.
      const avisos = [...r.mensajes];
      if (r.encolados < listos.length) {
        avisos.push(
          `${listos.length - r.encolados} vídeo(s) reconocidos NO se encolaron ` +
            "(en productos de plazos hacen falta los dos clips).",
        );
      }
      if (sinAsignar.length) {
        avisos.push(`${sinAsignar.length} vídeo(s) sin reconocer: asígnalos abajo.`);
      }
      return { encolados: r.encolados, sinAsignar, avisos };
    },
    [confirmar, folder, source],
  );

  /** Pide el reparto con los tokens ya subidos y decide si repasar o encolar. */
  const repartirYSeguir = useCallback(
    async (tokens: string[], nombres: Map<string, string>, auto: boolean, vozElegida: Sexo) => {
      setReconociendo(true);
      try {
        const r = await repartir.mutateAsync({ source, folder, tokens });
        const items = r.items.map((x) => ({
          ...x,
          archivo: nombres.get(x.token) ?? x.archivo,
        }));
        if (auto) {
          const res = await encolarDirecto(items, vozElegida);
          setAvisos(res.avisos);
          if (!res.sinAsignar.length) {
            await borrarLote(loteId);
            setReparto(null);
            setPendiente(null);
            return;
          }
          // Quedan sin reconocer: se dejan EN PANTALLA para asignarlos, no se
          // descartan. Los ya encolados no vuelven a salir.
          setReparto(res.sinAsignar);
          await guardarReparto(loteId, res.sinAsignar);
          return;
        }
        setReparto(items);
        await guardarReparto(loteId, items);
        toast.success(`${r.reconocidos}/${items.length} vídeos reconocidos. Repasa y confirma.`);
      } finally {
        setReconociendo(false);
      }
    },
    [encolarDirecto, folder, loteId, repartir, source],
  );

  /** Sube lo que falte de la tanda guardada y sigue con el reparto.
   *
   *  Vale tanto para empezar como para retomar: lee de IndexedDB los ficheros
   *  sin token, así que un vídeo ya subido no vuelve a viajar.
   */
  const procesarPendientes = useCallback(async () => {
    const meta = await leerLote(loteId);
    if (!meta) return;
    const ficheros = await ficherosDe(loteId);
    if (!ficheros.length) return;

    const ctrl = new AbortController();
    cancelar.current = ctrl;
    const nombres = new Map<string, string>();
    for (const f of ficheros) if (f.token) nombres.set(f.token, f.nombre);

    try {
      const faltan = ficheros.filter((f) => !f.token && f.blob);
      for (const [i, f] of faltan.entries()) {
        setProgreso({ n: ficheros.length - faltan.length + i + 1, total: ficheros.length, pct: 0 });
        const tok = await subirUno({
          source,
          folder,
          file: f.blob as Blob,
          nombre: f.nombre,
          root,
          senal: ctrl.signal,
          onProgreso: (pct) =>
            setProgreso({ n: ficheros.length - faltan.length + i + 1, total: ficheros.length, pct }),
        });
        await marcarToken(loteId, f.idx, tok);
        nombres.set(tok, f.nombre);
      }
      // Se limpia el progreso ANTES de reconocer: si no, el botón se quedaba
      // clavado en "Vídeo 3 de 3 · 100%" mientras la IA pensaba, que es la
      // parte que más tarda.
      setProgreso(null);
      setPendiente(null);
      const tokens = (await ficherosDe(loteId)).map((f) => f.token).filter(Boolean) as string[];
      await repartirYSeguir(tokens, nombres, meta.auto, meta.sexo);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      // Cortar al salir de la pantalla no es un error que enseñar.
      if (!ctrl.signal.aborted) toast.error(msg);
      const quedan = await ficherosDe(loteId);
      const subidos = quedan.filter((f) => f.token).length;
      if (quedan.length) setPendiente({ subidos, total: quedan.length });
    } finally {
      setProgreso(null);
      setReconociendo(false);
      cancelar.current = null;
    }
  }, [folder, loteId, repartirYSeguir, root, source]);

  async function enviar(files: File[]) {
    if (!files.length) return;
    const auto = !confirmarAntes;
    setReparto(null);
    setAvisos([]);

    const meta = {
      id: loteId,
      source,
      folder,
      root,
      modo: (soportaBgFetch() ? "bg" : "xhr") as "bg" | "xhr",
      auto,
      sexo,
      base: baseApi(),
      apiKey: claveApi(),
    };

    // Si la app sabe subir por su cuenta, se le deja a ella: su servicio en
    // primer plano aguanta la pantalla apagada mejor que Background Fetch, que
    // lo corta Chrome. En el navegador y en la app vieja esto no existe y se
    // sigue por el camino de siempre.
    //
    // Se le pregunta ANTES de guardar nada: cuando sube la app, los ficheros
    // los tiene ella y no hace falta la copia en el navegador. Guardarla era
    // meter varios vídeos de 20 MB en el almacén del WebView, que tiene menos
    // sitio que Chrome —y si eso falla, fallaba la tanda entera antes de
    // empezar, sin decir nada.
    if (haySubidaNativa()) {
      const lanzada = subirConLaApp({
        url: urlSubidaLote(root),
        apiKey: claveApi(),
        // `?i=` es como el servidor sabe qué respuesta es de qué fichero:
        // todas van a la misma dirección (igual que con Background Fetch).
        tareas: files.map((f, i) => ({
          nombre: f.name,
          url: `${urlSubidaLote(root)}?i=${i}`,
          campos: { source, folder },
        })),
      });
      if (lanzada) {
        await crearLote(meta, files, false);
        setEnSegundoPlano(true);
        setPendiente({ subidos: 0, total: files.length });
        toast.success("Subiendo con la app: ya puedes bloquear el móvil.");
        return;
      }
      toast.warning("La app no pudo con la tanda; la subo desde aquí.");
    }

    await crearLote(meta, files);

    // Camino bueno: el sistema se encarga y la app puede cerrarse.
    if (soportaBgFetch()) {
      const reg = await lanzarEnSegundoPlano({
        loteId,
        url: urlSubidaLote(root),
        apiKey: claveApi(),
        source,
        folder,
        files,
      });
      if (reg) {
        setEnSegundoPlano(true);
        setPendiente({ subidos: 0, total: files.length });
        toast.success("Subiendo en segundo plano: ya puedes cerrar la app.");
        return;
      }
      await actualizarLote(loteId, { modo: "xhr" });
    }

    await procesarPendientes();
  }

  /** Lo que sube la app hay que RECOGERLO aquí.
   *
   *  Faltaba, y por eso "Subir todos los vídeos" no hacía nada en la APK nueva:
   *  la app subía los ficheros y ahí se quedaba la cosa. Quien reparte los
   *  vídeos entre productos y los encola es la web, y sin los tokens de vuelta
   *  no tenía con qué. Con Background Fetch no pasaba porque de eso se encarga
   *  el Service Worker (`sw-subidas.js`), que sí hace los tres pasos.
   *
   *  Se casa por NOMBRE de fichero, que es lo único que viaja por el puente
   *  (los bytes se quedan en la app).
   */
  const recogerDeLaApp = useCallback(
    async (nombre: string, token: string) => {
      const meta = await leerLote(loteId);
      if (!meta) return;
      const ficheros = await ficherosDe(loteId);
      const suyo = ficheros.find((f) => f.nombre === nombre && !f.token);
      if (!suyo) return;
      if (!token) {
        toast.error(`No se pudo subir ${nombre}`);
        return;
      }
      await marcarToken(loteId, suyo.idx, token);

      const ahora = await ficherosDe(loteId);
      const conToken = ahora.filter((f) => f.token);
      setPendiente({ subidos: conToken.length, total: ahora.length });
      // Solo cuando están TODOS: repartir a medias dejaría fuera a los que
      // siguen subiendo y habría que volver a hacerlo entero.
      if (conToken.length < ahora.length) return;

      setEnSegundoPlano(false);
      setPendiente(null);
      const nombres = new Map<string, string>();
      for (const f of conToken) if (f.token) nombres.set(f.token, f.nombre);
      await repartirYSeguir(
        conToken.map((f) => f.token as string), nombres, meta.auto, meta.sexo,
      );
    },
    [loteId, repartirYSeguir],
  );

  // Fichero a fichero mientras la pantalla está abierta.
  useEffect(() => alSubirCadaFichero((nombre, respuesta) => {
    let token = "";
    try {
      token = String((JSON.parse(respuesta) as { token?: string })?.token || "");
    } catch {
      // Respuesta rota: se trata como fichero que no subió.
    }
    void recogerDeLaApp(nombre, token);
  }), [recogerDeLaApp]);

  // Y de golpe al volver, si la tanda acabó con la app cerrada: la app guarda
  // las respuestas del servidor y las entrega al reaparecer la pantalla. Cada
  // una trae `archivo` (el nombre que se subió), que es con lo que se casa.
  useEffect(() => alTerminarLaApp((respuestas) => {
    void (async () => {
      for (const r of respuestas) {
        const dato = r as { archivo?: string; token?: string };
        if (dato?.archivo) await recogerDeLaApp(dato.archivo, String(dato.token || ""));
      }
    })();
  }), [recogerDeLaApp]);

  // Al abrir la pantalla: ¿había una tanda a medias?
  useEffect(() => {
    let vivo = true;
    void (async () => {
      const meta = await leerLote(loteId);
      if (!vivo || !meta) return;
      if (meta.reparto?.length) {
        setReparto(meta.reparto as LoteItem[]);
        setAbierto(true);
        return;
      }
      const ficheros = await ficherosDe(loteId);
      if (!vivo || !ficheros.length) return;
      const enMarcha = await tandaEnMarcha(loteId);
      if (!vivo) return;
      setPendiente({ subidos: ficheros.filter((f) => f.token).length, total: ficheros.length });
      setAbierto(true);
      if (enMarcha) setEnSegundoPlano(true);
    })();
    return () => {
      vivo = false;
      cancelar.current?.abort();
    };
  }, [loteId]);

  // Lo que cuenta el Service Worker cuando termina con la app cerrada.
  useEffect(() => {
    return escucharAvisos((a) => {
      if (a.loteId !== loteId) return;
      setEnSegundoPlano(false);
      if (a.tipo === "lote-encolado") {
        toast.success(`${a.encolados} vídeo(s) ya en la cola.`);
        setPendiente(null);
        setReparto(null);
        return;
      }
      if (a.tipo === "lote-cancelado") {
        toast.warning("Subida cancelada.");
      }
      if (a.tipo === "lote-fallo") {
        toast.error("No se pudo subir ningún vídeo.");
      }
      // Quedan tokens o ficheros: que la pantalla los recoja.
      void (async () => {
        const meta = await leerLote(loteId);
        if (meta?.reparto?.length) {
          setReparto(meta.reparto as LoteItem[]);
          setPendiente(null);
          return;
        }
        const ficheros = await ficherosDe(loteId);
        if (!ficheros.length) {
          setPendiente(null);
          return;
        }
        const subidos = ficheros.filter((f) => f.token).length;
        setPendiente({ subidos, total: ficheros.length });
        // Todo subido y sin repaso: solo falta reconocer, y eso se hace ya.
        if (subidos === ficheros.length) void procesarPendientes();
      })();
    });
  }, [loteId, procesarPendientes]);

  // Aviso al cerrar mientras sube desde la pantalla. En el móvil no llega
  // (por eso existe todo lo de arriba), pero en escritorio evita el susto.
  useEffect(() => {
    if (!progreso && !reconociendo) return;
    const avisar = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", avisar);
    return () => window.removeEventListener("beforeunload", avisar);
  }, [progreso, reconociendo]);

  const listos = (reparto ?? []).filter((i) => i.producto).length;
  // El repaso, agrupado por producto y con los clips numerados.
  const filas = useMemo(
    () => ordenarPorProducto(reparto ?? [], productos, todosDobles),
    [productos, reparto, todosDobles],
  );

  function cambiar(i: number, producto: string) {
    setReparto((prev) => {
      const nuevo = (prev ?? []).map((x, n) => (n === i ? { ...x, producto } : x));
      void guardarReparto(loteId, nuevo);
      return nuevo;
    });
  }

  async function descartarPendiente() {
    cancelar.current?.abort();
    const enMarcha = await tandaEnMarcha(loteId);
    await enMarcha?.abort().catch(() => false);
    await borrarLote(loteId);
    setPendiente(null);
    setEnSegundoPlano(false);
    setReparto(null);
    toast.info("Tanda descartada.");
  }

  return (
    <section
      className={
        sinMarco ? "space-y-2" : "space-y-2 rounded-xl border border-border/60 bg-card p-3"
      }
    >
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className={
          sinMarco
            ? "flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2.5 text-xs font-semibold text-white transition hover:bg-emerald-600"
            : "flex w-full items-center justify-between text-left"
        }
      >
        <span className="flex items-center gap-1.5 text-sm font-semibold">
          <Sparkles className={`h-4 w-4 ${sinMarco ? "" : "text-emerald-500"}`} />
          Subir todos los vídeos
        </span>
        <span className={`text-[11px] ${sinMarco ? "" : "text-muted-foreground"}`}>
          {abierto ? "▾" : "▸"}
        </span>
      </button>

      {abierto && (
        <div className="space-y-2">
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            Suelta los vídeos de la carpeta y se reparten solos. No hace falta
            que estén todos: los productos sin vídeo se quedan como están, y si
            alguno no se reconoce lo asignas tú.
          </p>

          {/* Con el check quitado no hay repaso, así que la voz hay que
              elegirla ANTES de soltar los vídeos. */}
          <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-border/60 p-2">
            <input
              type="checkbox"
              checked={confirmarAntes}
              onChange={(e) => setConfirmarAntes(e.target.checked)}
              disabled={subiendo}
              className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-emerald-500"
            />
            <span className="min-w-0">
              <span className="block text-[11px] font-semibold">Confirmar antes de editar</span>
              <span className="block text-[10px] text-muted-foreground">
                {confirmarAntes
                  ? "Verás qué vídeo ha puesto en cada producto y confirmas tú."
                  : "Va directo: reparte y manda a editar sin preguntar."}
              </span>
            </span>
          </label>

          <div className="flex rounded-md border border-border/60 p-0.5 text-[11px]">
            {(["auto", "hombre", "mujer"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => {
                  setSexo(s);
                  void actualizarLote(loteId, { sexo: s });
                }}
                className={`flex-1 rounded px-1.5 py-1 transition ${
                  sexo === s ? "bg-emerald-500 font-semibold text-white" : "text-muted-foreground"
                }`}
              >
                {s === "auto" ? "🖐️ Auto" : s === "hombre" ? "👨 Hombre" : "👩 Mujer"}
              </button>
            ))}
          </div>

          {/* Qué NO se encoló y por qué. Se queda hasta que se cierre: la
              queja fue "subí 5 y solo se editan 4" sin saber cuál faltaba. */}
          {avisos.length > 0 && (
            <div className="space-y-1 rounded-lg border border-amber-500/50 bg-amber-500/5 p-2">
              <div className="flex items-start justify-between gap-2">
                <p className="text-[11px] font-semibold text-amber-500">Revisa esto</p>
                <button
                  type="button"
                  onClick={() => setAvisos([])}
                  className="text-[10px] text-muted-foreground hover:text-foreground"
                >
                  cerrar
                </button>
              </div>
              {avisos.map((a) => (
                <p key={a} className="text-[10px] leading-relaxed text-muted-foreground">
                  · {a}
                </p>
              ))}
            </div>
          )}

          {/* Tanda a medias: o se retoma (sin volver a subir lo que ya está) o
              se tira. Es lo que salva la subida cuando Android mata la app. */}
          {pendiente && !progreso && !reconociendo && (
            <div className="space-y-1.5 rounded-lg border border-amber-500/50 bg-amber-500/5 p-2">
              <p className="text-[11px] font-semibold text-amber-500">
                {enSegundoPlano
                  ? `Subiendo en segundo plano · ${pendiente.total} vídeo(s)`
                  : `Tanda a medias: ${pendiente.subidos}/${pendiente.total} subidos`}
              </p>
              <p className="text-[10px] text-muted-foreground">
                {enSegundoPlano
                  ? "Puedes cerrar la app: el móvil sigue subiendo y al volver estará listo."
                  : "Se retoma donde iba: lo ya subido no vuelve a viajar."}
              </p>
              <div className="grid grid-cols-2 gap-1.5">
                {!enSegundoPlano && (
                  <button
                    type="button"
                    onClick={() => void procesarPendientes()}
                    className="flex items-center justify-center gap-1.5 rounded-md bg-amber-500 px-2 py-1.5 text-[11px] font-semibold text-white transition hover:bg-amber-600"
                  >
                    <RotateCw className="h-3 w-3" /> Retomar
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void descartarPendiente()}
                  className={`flex items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1.5 text-[11px] text-muted-foreground transition hover:text-foreground ${
                    enSegundoPlano ? "col-span-2" : ""
                  }`}
                >
                  <Trash2 className="h-3 w-3" /> Descartar
                </button>
              </div>
            </div>
          )}

          <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600">
            {progreso ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Vídeo{" "}
                {progreso.n} de {progreso.total} · {progreso.pct}%
              </>
            ) : reconociendo ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Reconociendo los
                productos…
              </>
            ) : enSegundoPlano ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Subiendo en segundo plano…
              </>
            ) : (
              <>
                <Upload className="h-3.5 w-3.5" />{" "}
                {elegidos.length
                  ? `${elegidos.length} elegido${elegidos.length === 1 ? "" : "s"} · cambiar`
                  : "Elegir vídeos"}
              </>
            )}
            <input
              type="file"
              accept="video/*"
              multiple
              disabled={subiendo}
              className="hidden"
              onChange={(e) => {
                const f = Array.from(e.target.files ?? []);
                e.target.value = "";
                // Que el selector no devuelva nada hay que DECIRLO. Si no, se
                // confunde con "la web no se ha enterado" y no hay forma de
                // saber cuál de las dos cosas ha pasado.
                if (!f.length) {
                  toast.error("El selector no devolvió ningún vídeo. Vuelve a intentarlo.");
                  return;
                }
                // No se sube al elegir: primero se enseña qué se ha cogido.
                // Elegir diez vídeos y que la pantalla no acuse recibo deja sin
                // saber si el selector devolvió algo o si falló la subida.
                setElegidos(f);
              }}
            />
          </label>

          {/* Lo elegido, antes de mandarlo. */}
          {elegidos.length > 0 && !subiendo && (
            <div className="space-y-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-2">
              <p className="text-[11px] font-semibold text-emerald-500">
                {elegidos.length} vídeo{elegidos.length === 1 ? "" : "s"} elegido
                {elegidos.length === 1 ? "" : "s"}
              </p>
              <p className="max-h-24 overflow-y-auto break-words text-[10px] leading-tight text-muted-foreground">
                {elegidos.map((f) => f.name).join(" · ")}
              </p>
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    const f = elegidos;
                    setElegidos([]);
                    // El error se ENSEÑA. Antes iba en un `void` suelto y, si
                    // reventaba —guardar los vídeos en el navegador sin sitio,
                    // por ejemplo—, no pasaba nada visible: ni subía ni avisaba.
                    void enviar(f).catch((e) => {
                      setElegidos(f);
                      toast.error(
                        e instanceof Error ? e.message : "No se pudo empezar la subida",
                      );
                    });
                  }}
                  className="flex items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600"
                >
                  <Upload className="h-3.5 w-3.5" /> Subir {elegidos.length}
                </button>
                <button
                  type="button"
                  onClick={() => setElegidos([])}
                  className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
                >
                  <Trash2 className="h-3 w-3" /> Quitar
                </button>
              </div>
            </div>
          )}

          {reparto && (
            <div className="space-y-1.5">
              {filas.map(({ it, idx: i, ficha, doble, clip, cuantos, falta, abreGrupo }) => {
                const asignado = conFoto.find((p) => p.producto === it.producto);
                return (
                  <div
                    key={it.token}
                    className={`space-y-1.5 rounded-lg border p-2 ${
                      it.producto ? "border-border/60" : "border-amber-500/50 bg-amber-500/5"
                    } ${!abreGrupo ? "-mt-1 border-t-0" : ""}`}
                  >
                    {/* De un vistazo: si el producto va de plazos y cuál de sus
                        dos clips es este. Sin esto había que abrir la ficha
                        para saber por qué un producto llevaba dos vídeos. */}
                    {(doble || falta) && (
                      <div className="flex flex-wrap items-center gap-1">
                        {ficha?.modo_plazos && (
                          <span className="rounded bg-indigo-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-400">
                            💳 Plazos
                          </span>
                        )}
                        {clip > 0 && (
                          <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-sky-400">
                            Clip {clip} de {cuantos}
                          </span>
                        )}
                        {falta && (
                          <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-500">
                            {cuantos > 2
                              ? `este guion pide ${cuantos} clips · no se editará`
                              : "falta el otro clip · no se editará"}
                          </span>
                        )}
                      </div>
                    )}

                    <div className="flex gap-2">
                      {/* El vídeo, para poder verlo: cuando no lo reconoce, el
                          nombre del fichero no dice absolutamente nada. */}
                      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                      <video
                        src={archivoLoteUrl(root, it.token)}
                        controls
                        preload="metadata"
                        playsInline
                        className="h-24 w-16 shrink-0 rounded border border-border/60 bg-black object-cover"
                      />
                      <div className="min-w-0 flex-1 space-y-1">
                        <p className="truncate text-[10px] text-muted-foreground">
                          {it.archivo}
                        </p>
                        {asignado ? (
                          <div className="flex items-center gap-1.5">
                            {asignado.clean_photo_id && (
                              /* eslint-disable-next-line @next/next/no-img-element */
                              <img
                                src={fotoUrl(source, folder, asignado.clean_photo_id)}
                                alt={asignado.producto}
                                className="h-10 w-10 rounded border border-emerald-500/60 object-cover"
                              />
                            )}
                            <span className="min-w-0 flex-1 truncate text-[11px] font-semibold">
                              {asignado.producto} · {asignado.titulo || "sin título"}
                            </span>
                          </div>
                        ) : (
                          <p className="text-[10px] text-amber-500">
                            No lo ha reconocido: elígelo abajo o déjalo fuera.
                          </p>
                        )}
                        {it.por_que && (
                          <p className="text-[10px] text-muted-foreground">{it.por_que}</p>
                        )}
                      </div>
                    </div>

                    {/* Las fotos de los productos, para elegir mirando y no
                        leyendo. La asignada va marcada. */}
                    <div className="flex gap-1 overflow-x-auto pb-1">
                      <button
                        type="button"
                        onClick={() => cambiar(i, "")}
                        className={`shrink-0 rounded border px-2 py-1 text-[10px] ${
                          it.producto
                            ? "border-border/60 text-muted-foreground"
                            : "border-amber-500 text-amber-500"
                        }`}
                      >
                        fuera
                      </button>
                      {conFoto.map((p) => (
                        <button
                          key={p.producto}
                          type="button"
                          onClick={() => cambiar(i, p.producto)}
                          title={`${p.producto} · ${p.titulo ?? ""}`}
                          className={`relative shrink-0 rounded border ${
                            it.producto === p.producto
                              ? "border-emerald-500 ring-1 ring-emerald-500"
                              : "border-border/60"
                          }`}
                        >
                          {p.clean_photo_id ? (
                            /* eslint-disable-next-line @next/next/no-img-element */
                            <img
                              src={fotoUrl(source, folder, p.clean_photo_id)}
                              alt={p.producto}
                              className="h-12 w-12 rounded object-cover"
                            />
                          ) : (
                            <span className="flex h-12 w-12 items-center justify-center text-[10px]">
                              {p.producto}
                            </span>
                          )}
                          <span className="absolute bottom-0 left-0 rounded-br rounded-tl bg-black/70 px-1 text-[9px] text-white">
                            {p.producto}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}

              <button
                type="button"
                disabled={confirmar.isPending || !listos}
                onClick={() =>
                  confirmar.mutate(
                    {
                      source,
                      folder,
                      items: (reparto ?? [])
                        .filter((i) => i.producto)
                        .map((i) => ({ token: i.token, producto: i.producto })),
                      sexo,
                      con_gancho: true,
                      con_titulo: true,
                      con_cta: true,
                      con_flecha: true,
                    },
                    {
                      onSuccess: (r) => {
                        toast.success(`${r.encolados} vídeo(s) en la cola, editando…`);
                        const avisosDelServidor = [...r.mensajes];
                        if (r.encolados < listos) {
                          avisosDelServidor.push(
                            `${listos - r.encolados} vídeo(s) NO se encolaron ` +
                              "(en productos de plazos hacen falta los dos clips).",
                          );
                        }
                        setAvisos(avisosDelServidor);
                        setReparto(null);
                        void borrarLote(loteId);
                      },
                      onError: (e) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                    },
                  )
                }
                className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
              >
                {confirmar.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Encolando…
                  </>
                ) : (
                  <>Mandar a editar ({listos})</>
                )}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
