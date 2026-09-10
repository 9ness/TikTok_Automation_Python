"use client";

import { PantallaRopa } from "@/components/tiktok-shop-ai-pro/PantallaRopa";

/** Moda Mujer · Marca Personal (sep 2026).
 *
 *  Los tres formatos con PERSONAJE FIJO: espejo multi escena, zapatos multi
 *  escena y zapatos vista POV. Pantalla aparte de la de personajes aleatorios
 *  por lo mismo que mujer y hombre están separadas — es otra cuenta de TikTok,
 *  y se trabaja una a la vez. Todo lo demás (catálogo, fotos, textos, pasos)
 *  es el mismo componente. */
export default function ModaMujerMarcaPage() {
  return <PantallaRopa variante="web" sexo="mujer" modalidad="marca" />;
}
