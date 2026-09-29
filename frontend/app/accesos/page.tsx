"use client";

import { ExternalLink } from "lucide-react";

import { NavegadorRemoto } from "@/components/settings/NavegadorRemoto";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMe } from "@/lib/queries/auth";

/** Los enlaces a las cosas que viven en el servidor, en un solo sitio.
 *
 *  Antes cada dirección estaba en una nota o en la cabeza de alguien: el panel
 *  de IPTV, el navegador remoto… Aquí se abren con un toque desde el móvil.
 *  Para añadir otro acceso basta una entrada más en `ENLACES`.
 *
 *  Solo el administrador: lo que cuelga de aquí lleva cuentas abiertas o
 *  gestiona otros proyectos.
 */
const ENLACES: { titulo: string; descripcion: string; href: string; icono: string }[] = [
  {
    titulo: "Panel de gestión IPTV",
    descripcion: "Panel de administración de iptv-nestor (Mora).",
    href: "https://tiktok-factory.tailbff00e.ts.net:10000",
    icono: "📺",
  },
];

export default function AccesosPage() {
  const me = useMe();
  const esAdmin = me.data?.rol === "admin";

  return (
    <div className="container mx-auto max-w-3xl space-y-6 p-4 sm:p-6 md:p-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">🔗 Accesos</h1>
        <p className="text-sm text-muted-foreground">
          Lo que vive en el servidor, a un toque: el navegador remoto para Flow y Magnific y los
          paneles de otros proyectos.
        </p>
      </header>

      {me.isSuccess && !esAdmin ? (
        <p className="text-sm text-muted-foreground">Esta pantalla es solo del administrador.</p>
      ) : (
        <>
          {/* El navegador con sus botones (encender / abrir / apagar). */}
          <NavegadorRemoto />

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Paneles</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {ENLACES.map((e) => (
                <div
                  key={e.href}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border/60 p-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {e.icono} {e.titulo}
                    </p>
                    <p className="text-[11px] text-muted-foreground">{e.descripcion}</p>
                  </div>
                  <Button asChild size="sm" variant="outline" className="shrink-0">
                    <a href={e.href} target="_blank" rel="noreferrer">
                      <ExternalLink className="mr-1.5 h-3.5 w-3.5" /> Abrir
                    </a>
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
