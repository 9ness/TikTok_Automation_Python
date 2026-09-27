"use client";

import { PantallaRopa } from "@/components/tiktok-shop-ai-pro/PantallaRopa";

/** Moda Mujer · Multimodo (sep 2026).
 *
 *  Los formatos MUDOS de 10s de su web (espejo solo música, camisetas,
 *  zapatillas, marca y los Vintage de botas y bolsos) juntos, con los
 *  catálogos de ropa, zapatos y accesorios. Pensado para un agente: en cada
 *  producto elige el formato que le va, y así la cuenta no se ancla en uno.
 *  "Todos los vídeos" junta lo hecho para bajarlo. */
export default function ModaMujerMultimodoPage() {
  return <PantallaRopa variante="web" sexo="mujer" modalidad="multimodo" />;
}
