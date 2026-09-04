"use client";

import { PantallaRopa } from "@/components/tiktok-shop-ai-pro/PantallaRopa";

/** El inventario de MUJER de la web del curso, que entra por ZIP en carpetas
 *  de diez. La prenda va PUESTA y grabada frente al espejo, así que aquí sí
 *  hay una persona y el prompt sale en femenino.
 *
 *  Pantalla aparte de la de hombre —misma en todo lo demás— porque cada
 *  inventario se publica desde una cuenta de TikTok distinta. */
export default function NichoRopaMujerPage() {
  return <PantallaRopa variante="web" sexo="mujer" />;
}
