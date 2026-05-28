import { redirect } from "next/navigation";

// La pestaña Hooks vive ahora dentro de /tiktok-shop/generate como un
// modo de la card chooser. Mantenemos esta ruta por si alguien la tiene
// bookmarkeada — redirige a la nueva ubicación.
export default function HooksRedirect() {
  redirect("/tiktok-shop/generate");
}
