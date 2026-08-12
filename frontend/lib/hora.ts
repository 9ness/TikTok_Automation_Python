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
