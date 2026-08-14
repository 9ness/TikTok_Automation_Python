/* Service Worker de subidas en segundo plano.
 *
 *  Sirve para UNA cosa: que soltar 10 vídeos de 30 MB desde el móvil no obligue
 *  a dejar la app abierta y encendida. Con Background Fetch (Chrome Android, y
 *  por tanto la APK) el sistema sigue subiendo aunque se cierre la app, y aquí
 *  se recogen los tokens que devolvió el servidor.
 *
 *  NO tiene handler de `fetch` a propósito: no cachea ni intercepta nada de la
 *  app: si lo hiciera, cualquier despiste dejaría la interfaz servida desde una
 *  caché vieja. Solo escucha los eventos de Background Fetch.
 *
 *  Si el lote es "automático" (sin repaso), también pide el reparto y lo
 *  confirma él mismo, así el operador cierra la app y al volver los vídeos ya
 *  están en la cola.
 *
 *  Los nombres de la base de datos están duplicados de `lib/loteIdb.ts` — un
 *  Service Worker no puede importar del bundle.
 */

const DB = "subidas-lote";
const VERSION = 1;
const STORE_LOTES = "lotes";
const STORE_FICHEROS = "ficheros";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

function abrir() {
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

function pedir(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function leerMeta(db, loteId) {
  const tx = db.transaction(STORE_LOTES, "readonly");
  return pedir(tx.objectStore(STORE_LOTES).get(loteId));
}

async function guardarMeta(db, meta) {
  const tx = db.transaction(STORE_LOTES, "readwrite");
  tx.objectStore(STORE_LOTES).put(meta);
  return new Promise((res) => {
    tx.oncomplete = () => res();
  });
}

async function guardarTokens(db, loteId, porIdx) {
  const tx = db.transaction(STORE_FICHEROS, "readwrite");
  const store = tx.objectStore(STORE_FICHEROS);
  for (const [idx, token] of porIdx) {
    const f = await pedir(store.get(`${loteId}#${idx}`));
    if (f) store.put({ ...f, token });
  }
  return new Promise((res) => {
    tx.oncomplete = () => res();
  });
}

async function ficherosDe(db, loteId) {
  const tx = db.transaction(STORE_FICHEROS, "readonly");
  const todos = await pedir(tx.objectStore(STORE_FICHEROS).index("loteId").getAll(loteId));
  return todos.sort((a, b) => a.idx - b.idx);
}

async function borrarLote(db, loteId) {
  const tx = db.transaction([STORE_LOTES, STORE_FICHEROS], "readwrite");
  tx.objectStore(STORE_LOTES).delete(loteId);
  const store = tx.objectStore(STORE_FICHEROS);
  const todos = await pedir(store.index("loteId").getAll(loteId));
  for (const f of todos) store.delete(f.id);
  return new Promise((res) => {
    tx.oncomplete = () => res();
  });
}

async function avisarPantallas(mensaje) {
  const cs = await self.clients.matchAll({ includeUncontrolled: true, type: "window" });
  for (const c of cs) c.postMessage(mensaje);
}

function cabeceras(meta) {
  const h = { "Content-Type": "application/json" };
  if (meta.apiKey) h["X-API-Key"] = meta.apiKey;
  return h;
}

/** Recoge los tokens de las respuestas. El índice viaja en la query (`?i=`)
 *  porque todas las peticiones van a la MISMA URL y el orden de `matchAll()`
 *  no está garantizado. */
async function tokensDeLaTanda(registration) {
  const records = await registration.matchAll();
  const out = [];
  for (const r of records) {
    let resp;
    try {
      resp = await r.responseReady;
    } catch {
      continue;
    }
    if (!resp || !resp.ok) continue;
    let data;
    try {
      data = await resp.json();
    } catch {
      continue;
    }
    if (!data || !data.token) continue;
    const idx = Number(new URL(r.request.url).searchParams.get("i"));
    if (Number.isNaN(idx)) continue;
    out.push([idx, data.token]);
  }
  return out;
}

async function alTerminar(event) {
  const loteId = event.registration.id;
  const db = await abrir();
  try {
    const meta = await leerMeta(db, loteId);
    if (!meta) return;

    const porIdx = await tokensDeLaTanda(event.registration);
    await guardarTokens(db, loteId, porIdx);

    const ficheros = await ficherosDe(db, loteId);
    const tokens = ficheros.map((f) => f.token).filter(Boolean);
    const faltan = ficheros.length - tokens.length;

    if (!tokens.length) {
      await event.updateUI({ title: "No se pudo subir ningún vídeo" });
      await avisarPantallas({ tipo: "lote-fallo", loteId });
      return;
    }

    // Repasar a mano: la pantalla se encarga cuando el operador vuelva.
    if (!meta.auto) {
      await event.updateUI({
        title: faltan
          ? `${tokens.length} vídeos subidos (${faltan} fallaron) · repásalos`
          : `${tokens.length} vídeos subidos · repásalos`,
      });
      await avisarPantallas({ tipo: "lote-subido", loteId });
      return;
    }

    // Automático: repartir y encolar sin que nadie mire.
    const base = meta.base || "";
    const rep = await fetch(`${base}${meta.root}/video/lote/repartir`, {
      method: "POST",
      credentials: "include",
      headers: cabeceras(meta),
      body: JSON.stringify({ source: meta.source, folder: meta.folder, tokens }),
    }).then((r) => (r.ok ? r.json() : null));

    const items = ((rep && rep.items) || [])
      .filter((i) => i.producto)
      .map((i) => ({ token: i.token, producto: i.producto }));

    if (!items.length) {
      await event.updateUI({ title: "Subidos, pero no reconoció ninguno · repásalos" });
      await avisarPantallas({ tipo: "lote-subido", loteId });
      return;
    }

    const conf = await fetch(`${base}${meta.root}/video/lote/confirmar`, {
      method: "POST",
      credentials: "include",
      headers: cabeceras(meta),
      body: JSON.stringify({
        source: meta.source,
        folder: meta.folder,
        items,
        sexo: meta.sexo || "auto",
        con_gancho: true,
        con_titulo: true,
        con_cta: true,
        con_flecha: true,
      }),
    }).then((r) => (r.ok ? r.json() : null));

    if (!conf) {
      // Se quedan los tokens guardados: al abrir la app se retoma el repaso.
      await guardarMeta(db, { ...meta, auto: false });
      await event.updateUI({ title: "Subidos · falta encolarlos, abre la app" });
      await avisarPantallas({ tipo: "lote-subido", loteId });
      return;
    }

    await borrarLote(db, loteId);
    await event.updateUI({ title: `${conf.encolados} vídeo(s) en la cola, editando` });
    await avisarPantallas({ tipo: "lote-encolado", loteId, encolados: conf.encolados });
  } finally {
    db.close();
  }
}

self.addEventListener("backgroundfetchsuccess", (event) => {
  event.waitUntil(alTerminar(event));
});

// Falló alguno: se guardan los que sí subieron y la pantalla reanuda el resto.
self.addEventListener("backgroundfetchfail", (event) => {
  event.waitUntil(alTerminar(event));
});

self.addEventListener("backgroundfetchabort", (event) => {
  event.waitUntil(avisarPantallas({ tipo: "lote-cancelado", loteId: event.registration.id }));
});

// Tocar la notificación abre la app donde estaba.
self.addEventListener("backgroundfetchclick", (event) => {
  event.waitUntil(self.clients.openWindow("/"));
});
