import type { Metadata } from "next";

import { LinksCuenta } from "@/components/links/LinksCuenta";

/** Página PÚBLICA de enlaces de afiliado de una cuenta multiplataforma
 *  (`/links/ama_shop`, `/links/viva_shop`): va en la bio de Instagram y
 *  Facebook. Sin login ni marco de la app (`lib/rutasPublicas.ts`). Los datos
 *  salen de `GET /api/v1/multiplataforma/links/<cuenta>` (público). */
export const metadata: Metadata = {
  title: "Mis productos",
  description: "Los productos de mis vídeos, con su enlace.",
  robots: { index: false, follow: false },
};

export default function LinksPage({
  params,
}: {
  params: { cuenta: string };
}) {
  return <LinksCuenta cuenta={params.cuenta} />;
}
