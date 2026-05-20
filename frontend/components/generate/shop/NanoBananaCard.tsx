"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Copy, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { usePreviewNanoBananaPrompt } from "@/lib/queries/generations";

import { PresetControls } from "./PresetControls";

interface NanoBananaConfig {
  n_angles: number;
  use_cases: string[];
}

const DEFAULT_CONFIG: NanoBananaConfig = {
  n_angles: 5,
  use_cases: ["packshot", "lifestyle", "macro"],
};

interface Props {
  userId: string;
  username: string;
  productId: string;
  hideTitle?: boolean;
}

export function NanoBananaCard({ userId, username, productId, hideTitle }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [config, setConfig] = useState<NanoBananaConfig>(DEFAULT_CONFIG);
  const [selectedPreset, setSelectedPreset] = useState<string>("");
  const [resultPrompt, setResultPrompt] = useState<string | null>(null);

  const preview = usePreviewNanoBananaPrompt();

  function applyConfig(cfg: Record<string, unknown>) {
    setConfig((prev) => ({ ...prev, ...(cfg as Partial<NanoBananaConfig>) }));
  }

  async function generate() {
    try {
      const res = await preview.mutateAsync({
        username,
        product_id: productId,
        n_angles: config.n_angles,
        use_cases: config.use_cases,
      });
      setResultPrompt(res.prompt);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error generando prompt Nano Banana.");
    }
  }

  async function copyToClipboard() {
    if (!resultPrompt) return;
    try {
      await navigator.clipboard.writeText(resultPrompt);
      toast.success("Prompt copiado al portapapeles.");
    } catch {
      toast.error("No se pudo copiar — selecciónalo manualmente.");
    }
  }

  function toggleUseCase(uc: string) {
    setConfig((c) =>
      c.use_cases.includes(uc)
        ? { ...c, use_cases: c.use_cases.filter((x) => x !== uc) }
        : { ...c, use_cases: [...c.use_cases, uc] },
    );
  }

  const USE_CASE_OPTIONS = ["packshot", "lifestyle", "macro", "in_hand", "outdoor", "studio"];

  return (
    <>
      <Card>
        <CardContent className="space-y-3 p-4 sm:p-5">
          {!hideTitle && (
            <div>
              <p className="text-lg font-semibold">🍌 Prompt Nano Banana</p>
              <p className="text-xs text-muted-foreground">
                Prompt para pedirle a Gemini fotos premium del producto. Copia, pega en
                Gemini chat + fotos source, y sube las generadas a "Photos generated".
                Coste ~$0.002 (Gemini 2.5 Flash).
              </p>
            </div>
          )}

          <PresetControls
            userId={userId}
            productId={productId}
            kind="nano_banana"
            selectedName={selectedPreset}
            onSelectName={setSelectedPreset}
            currentConfig={config as unknown as Record<string, unknown>}
            onLoadConfig={applyConfig}
          />

          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={generate} disabled={preview.isPending} className="flex-1">
              {preview.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              Generar prompt
            </Button>
            <Button variant="outline" size="sm" onClick={() => setExpanded((v) => !v)}>
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              {expanded ? "Ocultar" : "Configurar"}
            </Button>
          </div>

          {expanded && (
            <div className="space-y-3 border-t pt-3">
              <div className="space-y-1">
                <Label className="text-xs">Número de ángulos</Label>
                <Select
                  value={String(config.n_angles)}
                  onValueChange={(v) =>
                    setConfig((c) => ({ ...c, n_angles: Number(v) }))
                  }
                >
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[4, 5, 6, 7, 8].map((n) => (
                      <SelectItem key={n} value={String(n)}>{n} ángulos</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Estilos a pedir</Label>
                <div className="flex flex-wrap gap-1">
                  {USE_CASE_OPTIONS.map((uc) => {
                    const active = config.use_cases.includes(uc);
                    return (
                      <button
                        key={uc}
                        type="button"
                        onClick={() => toggleUseCase(uc)}
                        className={`rounded-full border px-2 py-0.5 text-[11px] ${
                          active
                            ? "border-primary bg-primary/15 text-primary"
                            : "border-border text-muted-foreground"
                        }`}
                      >
                        {uc}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={resultPrompt !== null} onOpenChange={(o) => !o && setResultPrompt(null)}>
        <DialogContent className="w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>🍌 Prompt Nano Banana listo</DialogTitle>
            <DialogDescription>
              Pega este prompt en Gemini chat con las fotos source. Las imágenes que te
              devuelva, súbelas en la pestaña "Photos generated" del producto.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            readOnly
            value={resultPrompt ?? ""}
            className="min-h-[260px] font-mono text-xs"
            onFocus={(e) => e.currentTarget.select()}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setResultPrompt(null)}>
              Cerrar
            </Button>
            <Button onClick={copyToClipboard}>
              <Copy className="h-4 w-4" />
              Copiar prompt
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
