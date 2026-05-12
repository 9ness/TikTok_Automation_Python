import type { Metadata } from "next";
import { Rubik } from "next/font/google";

import "./globals.css";
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
          <div className="flex min-h-screen flex-col md:flex-row">
            <Sidebar />
            <main className="flex-1 overflow-y-auto bg-background">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
