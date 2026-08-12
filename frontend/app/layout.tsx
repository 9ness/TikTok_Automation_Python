import type { Metadata, Viewport } from "next";
import { Rubik } from "next/font/google";

import "./globals.css";
import { AppInstallBanner } from "@/components/layout/AppInstallBanner";
import { ChivatoCierres } from "@/components/layout/ChivatoCierres";
import { LoginGate } from "@/components/layout/LoginModal";
import { RestaurarPantalla } from "@/components/layout/RestaurarPantalla";
import { BarraCuota } from "@/components/layout/BarraCuota";
import { Sidebar } from "@/components/layout/Sidebar";
import { Providers } from "./providers";

// Rubik bold/black para el preview "CapCut style" del nicho Presidentes.
// Se expone como CSS var `var(--font-rubik)` para usarla puntualmente.
const rubik = Rubik({
  subsets: ["latin"],
  weight: ["700", "900"],
  variable: "--font-rubik",
  display: "swap",
});

export const metadata: Metadata = {
  title: "TikTok Automation",
  description: "Generación automatizada de vídeos virales para TikTok",
  // El manifest es lo que convierte la web en instalable: sin él Android no
  // ofrece "añadir a pantalla de inicio" y la APK (TWA) no arranca.
  manifest: "/manifest.json",
  icons: { icon: "/icon-192.png", apple: "/apple-touch-icon.png" },
  // iOS no lee el manifest: necesita sus propias metas para abrirse sin la
  // barra de Safari cuando se añade a la pantalla de inicio.
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "TikTok Auto",
  },
};

export const viewport: Viewport = {
  themeColor: "#000000",
  // `viewport-fit=cover` + los `env(safe-area-inset-*)` del CSS: en pantalla
  // completa (APK o instalada) no hay barra del navegador que aparte el
  // contenido de la muesca y de la barra de gestos.
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={rubik.variable} suppressHydrationWarning>
      <body className="antialiased" suppressHydrationWarning>
        <Providers>
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
                <div className="sticky top-[calc(3.5rem+env(safe-area-inset-top))] z-30 md:top-0">
                  <BarraCuota />
                </div>
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
        </Providers>
      </body>
    </html>
  );
}
