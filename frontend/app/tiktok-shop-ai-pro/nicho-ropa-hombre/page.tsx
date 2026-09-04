"use client";

import { PantallaRopa } from "@/components/tiktok-shop-ai-pro/PantallaRopa";

/** El inventario de HOMBRE de la web del curso. Igual que el de mujer salvo
 *  en los formatos: aquí hay cuatro (espejo, selfie y las dos situaciones de
 *  calle) y en mujer solo el del espejo, porque son los que él publica. */
export default function NichoRopaHombrePage() {
  return <PantallaRopa variante="web" sexo="hombre" />;
}
