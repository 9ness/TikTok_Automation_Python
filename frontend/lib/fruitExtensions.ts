/**
 * Persistencia local (localStorage) de historias de fruta ALARGADAS (20s/30s).
 *
 * El endpoint extend-fruit NO persiste en Redis (es síncrono y caro de
 * versionar en el modelo). Para que el operador no pierda el resultado al
 * recargar (sobre todo en móvil) y pueda reusarlo, lo guardamos en el
 * navegador, indexado por producto + preset base.
 *
 * Cascada: al cargar purgamos (a) las entradas cuyo preset base ya no existe
 * en el producto — esto cubre el "borrado al regenerar todos los presets",
 * porque al regenerar cambian los ids — y (b) las más viejas que `TTL_MS`.
 */
import type { FruitStoryPart } from "@/lib/types/product";

export interface SavedFruitExtension {
  presetId: string;
  presetName: string;
  parts: FruitStoryPart[];
  photo_filenames: string[];
  createdAt: number; // epoch ms
}

type ProductMap = Record<string, SavedFruitExtension>;

const KEY_PREFIX = "tiktok_shop.fruit_ext.v1.";
// Caducidad: 30 días. "Guardado al menos durante un tiempo".
const TTL_MS = 30 * 24 * 60 * 60 * 1000;

function keyFor(productId: string): string {
  return `${KEY_PREFIX}${productId}`;
}

function readRaw(productId: string): ProductMap {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(keyFor(productId));
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") return parsed as ProductMap;
  } catch {
    /* corrupto / bloqueado — ignora */
  }
  return {};
}

function writeRaw(productId: string, map: ProductMap): void {
  if (typeof window === "undefined") return;
  try {
    if (Object.keys(map).length === 0) {
      window.localStorage.removeItem(keyFor(productId));
    } else {
      window.localStorage.setItem(keyFor(productId), JSON.stringify(map));
    }
  } catch {
    /* quota / modo privado — silencia */
  }
}

/**
 * Devuelve las extensiones guardadas del producto tras purgar las huérfanas
 * (preset base ya no existe → cascada) y las caducadas. Reescribe si purgó.
 */
export function loadFruitExtensions(
  productId: string,
  validPresetIds: Iterable<string>,
): ProductMap {
  if (!productId) return {};
  const map = readRaw(productId);
  const valid = new Set(validPresetIds);
  const now = Date.now();
  let changed = false;
  const out: ProductMap = {};
  for (const [pid, ext] of Object.entries(map)) {
    if (!valid.has(pid)) {
      changed = true;
      continue; // cascada: el preset base ya no existe
    }
    if (typeof ext.createdAt === "number" && now - ext.createdAt > TTL_MS) {
      changed = true;
      continue; // caducada
    }
    out[pid] = ext;
  }
  if (changed) writeRaw(productId, out);
  return out;
}

/** Guarda (o sobrescribe) la extensión de un preset y devuelve el nuevo mapa. */
export function saveFruitExtension(
  productId: string,
  ext: SavedFruitExtension,
): ProductMap {
  const map = readRaw(productId);
  map[ext.presetId] = ext;
  writeRaw(productId, map);
  return map;
}

/** Borra la extensión de un preset y devuelve el nuevo mapa. */
export function deleteFruitExtension(
  productId: string,
  presetId: string,
): ProductMap {
  const map = readRaw(productId);
  delete map[presetId];
  writeRaw(productId, map);
  return map;
}
