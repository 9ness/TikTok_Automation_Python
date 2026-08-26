"use client";

import { PantallaRopa } from "@/components/tiktok-shop-ai-pro/PantallaRopa";

/** El catálogo de ropa de la web del curso, que entra por ZIP en carpetas de
 *  diez. La prenda va PUESTA y grabada frente al espejo, así que aquí sí hay
 *  una persona y el prompt sale en el sexo de la carpeta. */
export default function NichoRopaWebPage() {
  return <PantallaRopa variante="web" />;
}
