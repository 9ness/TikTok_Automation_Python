/** "14:32" a partir de un epoch en segundos. Cadena vacía si no hay hora.
 *
 *  Se enseña junto a "Subido" para poder comprobar que el toque entró: si
 *  vuelves a marcar el mismo producto y la hora cambia, quedó registrado.
 */
export function horaCorta(epoch: number | undefined | null): string {
  if (!epoch) return "";
  return new Date(epoch * 1000).toLocaleTimeString("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "17 ago, 14:32" a partir de una fecha ISO. Cadena vacía si no hay.
 *
 *  Es la fecha en la que el curso subió la foto al Drive: lo que dice si un
 *  producto es NUEVO en una carpeta que ya estaba trabajada.
 */
export function fechaCorta(iso: string | undefined | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("es-ES", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
