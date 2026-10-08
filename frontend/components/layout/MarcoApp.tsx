"use client";

import { usePathname } from "next/navigation";

import { AppInstallBanner } from "@/components/layout/AppInstallBanner";
import { BarraCuota } from "@/components/layout/BarraCuota";
import { ChivatoCierres } from "@/components/layout/ChivatoCierres";
import { FranjaCampanas } from "@/components/layout/FranjaCampanas";
import { LoginGate } from "@/components/layout/LoginModal";
import { RestaurarPantalla } from "@/components/layout/RestaurarPantalla";
import { Sidebar } from "@/components/layout/Sidebar";
import { esRutaPublica } from "@/lib/rutasPublicas";

/** El marco de la app (login, sidebar, barra de cuota…), salvo en las rutas
 *  PÚBLICAS (`lib/rutasPublicas.ts`, p. ej. `/links/<cuenta>`), que se pintan
 *  solas y sin pedir login. Antes vivía directamente en `app/layout.tsx`. */
export function MarcoApp({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (esRutaPublica(pathname)) return <>{children}</>;
  return (
    <LoginGate>
      <div className="flex min-h-screen flex-col md:flex-row">
        <Sidebar />
        {/* min-w-0 → permite que la columna flex encoja en desktop;
            overflow-x-hidden → red de seguridad móvil: ningún hijo ancho
            desborda la página entera (el scroll horizontal interno de
            tablas/etc. sigue funcionando dentro de su propio contenedor). */}
        <main className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto bg-background">
          {/* Lo que queda por publicar hoy, en el marco: el tope es de la
              CUENTA de TikTok, no de un nicho, así que tiene que verse
              desde cualquier pantalla, también al hacer scroll.
              En móvil se pega JUSTO DEBAJO de la cabecera (que mide
              3.5rem + el safe-area y va en z-40): con `top-0` se quedaba
              tapada por ella y no se veía. En escritorio no hay cabecera,
              así que va arriba del todo. */}
          {/* FIJA, no `sticky`: `main` tiene `overflow-y-auto` pero no
              altura acotada, así que quien hace scroll de verdad es la
              página — y un `sticky` dentro de `main` se va con el
              contenido (se veía flotando a media pantalla y desaparecía
              al bajar). Fija se queda pegada a la viewport siempre.
              En móvil, justo debajo de la cabecera; en escritorio, a la
              derecha de la barra lateral (16rem). */}
          <div className="fixed inset-x-0 top-[calc(3.5rem+env(safe-area-inset-top))] z-30 md:left-64 md:top-0">
            <BarraCuota />
            <FranjaCampanas />
          </div>
          {/* Hueco del mismo alto: sin esto la barra taparía lo primero
              de cada pantalla. La franja de campañas suma su alto con
              `--alto-campana` (0 cuando no sale). */}
          <div style={{ height: "calc(2rem + var(--alto-campana, 0px))" }} aria-hidden />
          {children}
        </main>
      </div>
      {/* Dentro del LoginGate: el aviso de instalar la app no tiene
          sentido en la pantalla de login. */}
      <AppInstallBanner />
      <RestaurarPantalla />
      {/* Temporal: cuenta al servidor cómo terminó la sesión anterior,
          para saber si la app la mata Android o la reventamos nosotros. */}
      <ChivatoCierres />
    </LoginGate>
  );
}
