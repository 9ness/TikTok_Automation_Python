"use client";

import Link from "next/link";

import { GeneratorWizard } from "@/components/generate/GeneratorWizard";
import { Button } from "@/components/ui/button";

export default function ShopGenerateAdvancedPage() {
  return (
    <div className="container mx-auto p-6 md:p-10">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Generador · Modo avanzado</h1>
          <p className="text-sm text-muted-foreground">
            Wizard de 8 pasos — usuario × producto × tier → encolar generación.
            Para flujo rápido con presets usa el modo simple.
          </p>
        </div>
        <Link href="/tiktok-shop/generate">
          <Button variant="outline" size="sm">
            ← Modo simple (presets)
          </Button>
        </Link>
      </div>
      <GeneratorWizard />
    </div>
  );
}
