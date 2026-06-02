import type { Metadata } from "next";
import { Rubik } from "next/font/google";

import "./globals.css";
import { LoginGate } from "@/components/layout/LoginModal";
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
                {children}
              </main>
            </div>
          </LoginGate>
        </Providers>
      </body>
    </html>
  );
}
