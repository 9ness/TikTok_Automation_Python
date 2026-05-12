import { Construction } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function PagePlaceholder({
  title,
  phase,
  description,
}: {
  title: string;
  phase: string;
  description?: string;
}) {
  return (
    <div className="container mx-auto p-6 md:p-10">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <Construction className="h-6 w-6 text-muted-foreground" />
            <CardTitle>{title}</CardTitle>
          </div>
          <CardDescription>
            {description ?? "Página en construcción."}{" "}
            <span className="font-mono text-xs">{phase}</span>
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          La interfaz se implementará en {phase}. Por ahora la API ya expone los endpoints
          necesarios; consulta <code className="rounded bg-muted px-1">/api/docs</code> en el
          backend para ver el contrato.
        </CardContent>
      </Card>
    </div>
  );
}
