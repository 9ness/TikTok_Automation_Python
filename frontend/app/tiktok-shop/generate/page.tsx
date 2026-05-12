"use client";

import { GeneratorWizard } from "@/components/generate/GeneratorWizard";

export default function ShopGeneratePage() {
  return (
    <div className="container mx-auto p-6 md:p-10">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Generador de vídeos</h1>
        <p className="text-sm text-muted-foreground">
          Wizard de 8 pasos: usuario × producto × tier → encolar generación.
        </p>
      </div>
      <GeneratorWizard />
    </div>
  );
}
