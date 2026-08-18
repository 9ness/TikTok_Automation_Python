"use client";

/** Lo que ve un `pro` (Ana, Mauro) en lugar del botón "Obtener textos".
 *
 *  Título, tienda, caption y precio salen de la foto del Drive del curso: son
 *  un dato del PRODUCTO, no de quien lo publica, y ya se guardan en el
 *  documento compartido de la carpeta. Cuestan llamadas de Gemini, así que los
 *  extrae `ness` una vez y los demás se los encuentran hechos — de ahí que
 *  aquí no haya botón, solo el estado.
 */
export function TextosDelAdmin({ hechos, total }: { hechos: number; total: number }) {
  const listos = total > 0 && hechos >= total;
  return (
    <div
      className={`rounded-lg border px-3 py-2.5 text-[11px] font-medium ${
        listos
          ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
          : "border-amber-500/60 bg-amber-500/10 text-amber-500"
      }`}
    >
      {listos ? (
        <>✅ Textos listos ({hechos}/{total}) — los prepara la cuenta de ness.</>
      ) : (
        <>
          ⏳ Faltan textos ({hechos}/{total}) — los prepara la cuenta de ness.
          Avísale y vuelve a entrar en la carpeta.
        </>
      )}
    </div>
  );
}
