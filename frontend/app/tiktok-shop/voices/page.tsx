"use client";

import { useState } from "react";
import { AlertCircle } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { VoiceCard } from "@/components/voices/VoiceCard";
import { useVoices } from "@/lib/queries/voices";

export default function ShopVoicesPage() {
  const [language, setLanguage] = useState<string>("__all__");
  const [gender, setGender] = useState<string>("__all__");
  const [includePresets, setIncludePresets] = useState(true);

  const voices = useVoices({
    language: language === "__all__" ? undefined : language,
    gender:
      gender === "__all__"
        ? undefined
        : (gender as "male" | "female" | "neutral"),
    include_presets: includePresets,
  });

  return (
    <div className="container mx-auto p-6 md:p-10">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Biblioteca de voces</h1>
        <p className="text-sm text-muted-foreground">
          Voces MiniMax presets + voces clonadas. Solo lectura por ahora.
        </p>
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-4">
        <div className="space-y-1">
          <Label className="text-xs">Idioma</Label>
          <Select value={language} onValueChange={setLanguage}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Todos</SelectItem>
              <SelectItem value="es">Español</SelectItem>
              <SelectItem value="en">English</SelectItem>
              <SelectItem value="pt">Português</SelectItem>
              <SelectItem value="fr">Français</SelectItem>
              <SelectItem value="it">Italiano</SelectItem>
              <SelectItem value="de">Deutsch</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Género</Label>
          <Select value={gender} onValueChange={setGender}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Todos</SelectItem>
              <SelectItem value="male">Male</SelectItem>
              <SelectItem value="female">Female</SelectItem>
              <SelectItem value="neutral">Neutral</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="include-presets"
            checked={includePresets}
            onCheckedChange={setIncludePresets}
          />
          <Label htmlFor="include-presets" className="text-sm">
            Incluir presets MiniMax
          </Label>
        </div>
      </div>

      {voices.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      )}

      {voices.isError && (
        <Card>
          <CardContent className="flex items-center gap-3 p-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <div>
              <p className="font-medium">Error cargando voces</p>
              <p className="text-sm text-muted-foreground">
                {voices.error?.message ?? "Sin detalles"}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {voices.data && voices.data.items.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-lg font-medium">Sin voces</p>
            <p className="text-sm text-muted-foreground">
              No hay voces que coincidan con los filtros.
            </p>
          </CardContent>
        </Card>
      )}

      {voices.data && voices.data.items.length > 0 && (
        <>
          <p className="mb-3 text-xs text-muted-foreground">
            {voices.data.total} voces disponibles
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {voices.data.items.map((v) => (
              <VoiceCard key={v.id} voice={v} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
