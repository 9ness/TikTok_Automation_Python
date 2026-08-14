"use client";

/** Guarda una tanda de vídeos EN EL MÓVIL mientras se sube.
 *
 *  Antes la subida vivía solo en la memoria de la pantalla: si el operador
 *  cerraba la app —o Android la mataba estando de fondo, que es lo que pasa de
 *  verdad— se perdían los ficheros ya subidos y el repaso hecho, y había que
 *  empezar de cero con 10-30 MB por vídeo.
 *
 *  Aquí se guardan los ficheros (IndexedDB sí admite Blob, localStorage no), el
 *  token que devolvió el servidor por cada uno y el reparto pendiente de
 *  confirmar. Al volver a abrir, la pantalla retoma por donde iba.
 *
 *  Lo comparte el Service Worker (`public/sw-subidas.js`), que escribe los
 *  tokens cuando la subida termina con la app cerrada — por eso los nombres de
 *  la base y de los almacenes están duplicados allí: no se pueden importar.
 */

const DB = "subidas-lote";
const VERSION = 1;
export const STORE_LOTES = "lotes";
export const STORE_FICHEROS = "ficheros";

export interface FicheroLote {
  /** `${loteId}#${idx}` — el Service Worker lo reconstruye igual. */
  id: string;
  loteId: string;
  idx: number;
  nombre: string;
  blob: Blob;
  /** Lo que devolvió el servidor. `null` = aún sin subir. */
  token: string | null;
}

export interface RepartoGuardado {
  token: string;
  archivo: string;
  producto: string;
  por_que: string;
}

export interface LoteMeta {
  id: string;
  source: string;
  folder: string;
  root: string;
  creado: number;
  total: number;
  /** Modo con el que se lanzó: `bg` = Background Fetch (sigue con la app
   *  cerrada), `xhr` = subida normal desde la pantalla. */
  modo: "bg" | "xhr";
  /** Sin repaso: repartir y encolar directamente. Lo hace el Service Worker
   *  si la subida acabó con la app cerrada. */
  auto: boolean;
  /** Voz elegida para la edición (se decide ANTES de subir cuando va en
   *  automático, porque luego no hay pantalla donde elegirla). */
  sexo: "auto" | "hombre" | "mujer";
  /** Lo que el Service Worker necesita para hablar con la API él solo. */
  base: string;
  apiKey: string;
  /** Repaso ya propuesto por la IA y todavía sin confirmar. */
  reparto?: RepartoGuardado[] | null;
}

function abrir(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_LOTES)) {
        db.createObjectStore(STORE_LOTES, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains(STORE_FICHEROS)) {
        const s = db.createObjectStore(STORE_FICHEROS, { keyPath: "id" });
        s.createIndex("loteId", "loteId");
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function esperar<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** Todo lo de aquí es "mejor esfuerzo": si el navegador no deja usar
 *  IndexedDB (modo privado, cuota llena), la subida tiene que seguir
 *  funcionando aunque luego no se pueda retomar. */
async function conDb<T>(fn: (db: IDBDatabase) => Promise<T>, sino: T): Promise<T> {
  try {
    const db = await abrir();
    try {
      return await fn(db);
    } finally {
      db.close();
    }
  } catch {
    return sino;
  }
}

export function idDeLote(root: string, source: string, folder: string): string {
  // Un lote por carpeta y nicho: si se vuelve a soltar vídeos en la misma
  // carpeta, se pisa el anterior en vez de acumular tandas zombis.
  return `${root}|${source}|${folder}`;
}

export async function crearLote(
  meta: Omit<LoteMeta, "creado" | "total" | "reparto">,
  files: File[],
): Promise<void> {
  await conDb(async (db) => {
    const tx = db.transaction([STORE_LOTES, STORE_FICHEROS], "readwrite");
    const lotes = tx.objectStore(STORE_LOTES);
    const ficheros = tx.objectStore(STORE_FICHEROS);
    // Limpia lo que hubiera de esa misma carpeta antes de empezar.
    const viejos = await esperar<FicheroLote[]>(
      ficheros.index("loteId").getAll(meta.id) as IDBRequest<FicheroLote[]>,
    );
    for (const v of viejos) ficheros.delete(v.id);
    lotes.put({ ...meta, creado: Date.now(), total: files.length, reparto: null } as LoteMeta);
    files.forEach((f, idx) => {
      ficheros.put({
        id: `${meta.id}#${idx}`,
        loteId: meta.id,
        idx,
        nombre: f.name,
        blob: f,
        token: null,
      } as FicheroLote);
    });
    await new Promise<void>((res, rej) => {
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
    });
  }, undefined);
}

export async function leerLote(id: string): Promise<LoteMeta | null> {
  return conDb(async (db) => {
    const tx = db.transaction(STORE_LOTES, "readonly");
    const m = await esperar<LoteMeta | undefined>(
      tx.objectStore(STORE_LOTES).get(id) as IDBRequest<LoteMeta | undefined>,
    );
    return m ?? null;
  }, null);
}

export async function ficherosDe(loteId: string): Promise<FicheroLote[]> {
  return conDb(async (db) => {
    const tx = db.transaction(STORE_FICHEROS, "readonly");
    const todos = await esperar<FicheroLote[]>(
      tx.objectStore(STORE_FICHEROS).index("loteId").getAll(loteId) as IDBRequest<FicheroLote[]>,
    );
    return todos.sort((a, b) => a.idx - b.idx);
  }, []);
}

export async function marcarToken(loteId: string, idx: number, token: string): Promise<void> {
  await conDb(async (db) => {
    const tx = db.transaction(STORE_FICHEROS, "readwrite");
    const store = tx.objectStore(STORE_FICHEROS);
    const f = await esperar<FicheroLote | undefined>(
      store.get(`${loteId}#${idx}`) as IDBRequest<FicheroLote | undefined>,
    );
    if (f) store.put({ ...f, token });
    await new Promise<void>((res) => {
      tx.oncomplete = () => res();
    });
  }, undefined);
}

export async function actualizarLote(loteId: string, parcial: Partial<LoteMeta>): Promise<void> {
  await conDb(async (db) => {
    const tx = db.transaction(STORE_LOTES, "readwrite");
    const store = tx.objectStore(STORE_LOTES);
    const m = await esperar<LoteMeta | undefined>(
      store.get(loteId) as IDBRequest<LoteMeta | undefined>,
    );
    if (m) store.put({ ...m, ...parcial });
    await new Promise<void>((res) => {
      tx.oncomplete = () => res();
    });
  }, undefined);
}

export async function guardarReparto(
  loteId: string,
  reparto: RepartoGuardado[] | null,
): Promise<void> {
  await conDb(async (db) => {
    const tx = db.transaction(STORE_LOTES, "readwrite");
    const store = tx.objectStore(STORE_LOTES);
    const m = await esperar<LoteMeta | undefined>(
      store.get(loteId) as IDBRequest<LoteMeta | undefined>,
    );
    if (m) store.put({ ...m, reparto });
    await new Promise<void>((res) => {
      tx.oncomplete = () => res();
    });
  }, undefined);
}

export async function borrarLote(loteId: string): Promise<void> {
  await conDb(async (db) => {
    const tx = db.transaction([STORE_LOTES, STORE_FICHEROS], "readwrite");
    tx.objectStore(STORE_LOTES).delete(loteId);
    const ficheros = tx.objectStore(STORE_FICHEROS);
    const todos = await esperar<FicheroLote[]>(
      ficheros.index("loteId").getAll(loteId) as IDBRequest<FicheroLote[]>,
    );
    for (const f of todos) ficheros.delete(f.id);
    await new Promise<void>((res) => {
      tx.oncomplete = () => res();
    });
  }, undefined);
}
