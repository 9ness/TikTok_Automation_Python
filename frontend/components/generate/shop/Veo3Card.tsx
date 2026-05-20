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
import { Input } from "@/components/ui/input";
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
import { usePreviewVeo3Prompt } from "@/lib/queries/generations";

import { PresetControls } from "./PresetControls";

const HOOK_CATEGORIES = [
  "curiosity",
  "problem_solution",
  "social_proof",
  "before_after",
  "shock",
  "tutorial",
];

interface Veo3Config {
  hook_category: string;
  hook_custom: string;
  target_audience: string;
}

const DEFAULT_CONFIG: Veo3Config = {
  hook_category: "curiosity",
  hook_custom: "",
  target_audience: "Generalista",
};

interface Props {
  userId: string;
  username: string;
  productId: string;
  hideTitle?: boolean;
}

export function Veo3Card({ userId, username, productId, hideTitle }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [config, setConfig] = useState<Veo3Config>(DEFAULT_CONFIG);
  const [selectedPreset, setSelectedPreset] = useState<string>("");
  const [resultPrompt, setResultPrompt] = useState<string | null>(null);
  const [resultMeta, setResultMeta] = useState<string>("");

  const preview = usePreviewVeo3Prompt();

  function patch<K extends keyof Veo3Config>(key: K, value: Veo3Config[K]) {
    setConfig((c) => ({ ...c, [key]: value }));
  }

  function applyConfig(cfg: Record<string, unknown>) {
    setConfig((prev) => ({ ...prev, ...(cfg as Partial<Veo3Config>) }));
  }

  async function generate() {
    try {
      const res = await preview.mutateAsync({
        username,
        product_id: productId,
        hook_category: config.hook_category,
        hook_custom: config.hook_custom.trim() || null,
        target_audience: config.target_audience.trim() || "Generalista",
      });
      setResultPrompt(res.prompt);
      setResultMeta(`Hook: "${res.hook_text}" · estilo: ${res.style}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error generando prompt Veo 3.");
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

  return (
    <>
      <Card>
        <CardContent className="space-y-3 p-4 sm:p-5">
          {!hideTitle && (
            <div>
              <p className="text-lg font-semibold">🟣 Prompt Veo 3</p>
              <p className="text-xs text-muted-foreground">
                Genera un prompt 8s al instante para pegar en Gemini chat con las fotos.
                Coste ~$0.004 (Gemini 2.5 Flash).
              </p>
            </div>
          )}

          <PresetControls
            userId={userId}
            productId={productId}
            kind="veo3"
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
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label className="text-xs">Hook · categoría</Label>
                  <Select
                    value={config.hook_category}
                    onValueChange={(v) => patch("hook_category", v)}
                  >
                    <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {HOOK_CATEGORIES.map((c) => (
                        <SelectItem key={c} value={c}>{c}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Audiencia</Label>
                  <Input
                    value={config.target_audience}
                    onChange={(e) => patch("target_audience", e.target.value)}
                  />
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Hook custom (opcional)</Label>
                <Input
                  value={config.hook_custom}
                  onChange={(e) => patch("hook_custom", e.target.value)}
                  placeholder="Sobrescribe la categoría con un hook concreto"
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={resultPrompt !== null} onOpenChange={(o) => !o && setResultPrompt(null)}>
        <DialogContent className="w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>🟣 Prompt Veo 3 listo</DialogTitle>
            <DialogDescription>
              Pega este prompt en Gemini chat junto a las fotos del producto. 8s, single shot, 9:16.
              {resultMeta ? ` · ${resultMeta}` : ""}
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
