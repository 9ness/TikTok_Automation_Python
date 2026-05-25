/** Helpers de formato de fecha que respetan la zona horaria del navegador.
 *  El backend guarda timestamps en UTC (`datetime.now(timezone.utc).isoformat()`).
 *  Mostrarlos crudos al usuario daría hora UTC en vez de su hora local
 *  (España UTC+1/+2, etc.).
 */

/** Formatea un ISO UTC como `dd/mm/yyyy HH:MM:SS` en la timezone local
 *  del navegador. Devuelve "" si la entrada no es parseable.
 *
 *  Ejemplo: "2026-05-25T11:10:50.123+00:00" en España DST →
 *  "25/05/2026 13:10:50".
 */
export function formatLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Versión corta sin segundos: `dd/mm HH:MM`. Útil para listas. */
export function formatLocalShort(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
