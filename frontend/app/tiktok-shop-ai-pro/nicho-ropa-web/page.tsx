import { redirect } from "next/navigation";

/** La pantalla vieja, cuando mujer y hombre compartían una con un selector.
 *
 *  Se queda como redirección y no se borra: está en el historial del navegador
 *  y en la pantalla de inicio del móvil de quien la tuviera anclada, y un 404
 *  ahí parece que el nicho ha desaparecido. */
export default function NichoRopaWebPage() {
  redirect("/tiktok-shop-ai-pro/nicho-ropa-mujer");
}
