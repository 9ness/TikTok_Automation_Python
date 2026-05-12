"use client";

import { useRef } from "react";
import { Loader2, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  type FontItem,
  useDeleteFont,
  useFonts,
  useUploadFont,
} from "@/lib/queries/fonts";

/** Selector universal de fuente. Usa el registry `/api/v1/fonts`. Lo
 *  comparten Presidentes, Subs sobre Vídeo y Quitar Copy. Permite subir
 *  un TTF/OTF nuevo desde el PC (se guarda en `assets/fonts/` y aparece
 *  al instante) y borrar fuentes bundled. Las fuentes de sistema no se
 *  pueden borrar. */
export function FontSelector({
  value,
  onChange,
  placeholder = "Selecciona fuente…",
  className,
  allowUpload = true,
}: {
  /** Path absoluto de la fuente seleccionada (lo que devuelve el registry). */
  value: string;
  onChange: (path: string) => void;
  placeholder?: string;
  className?: string;
  allowUpload?: boolean;
}) {
  const fonts = useFonts();
  const upload = useUploadFont();
  const remove = useDeleteFont();
  const inputRef = useRef<HTMLInputElement | null>(null);

  const items: FontItem[] = fonts.data?.items ?? [];
  const selected = items.find((f) => f.path === value);

  async function handleUpload(file: File) {
    try {
      const entry = await upload.mutateAsync(file);
      onChange(entry.path);
      toast.success(`Fuente '${entry.name}' añadida.`);
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Error al subir fuente.",
      );
    }
  }

  async function handleDelete() {
    if (!selected || selected.source !== "bundled") return;
    if (
      !window.confirm(
        `¿Borrar la fuente '${selected.name}' (${selected.filename})?`,
      )
    )
      return;
    try {
      await remove.mutateAsync(selected.filename);
      const fallback = items.find((f) => f.path !== selected.path);
      if (fallback) onChange(fallback.path);
      toast.success(`Fuente '${selected.name}' borrada.`);
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Error al borrar fuente.",
      );
    }
  }

  return (
    <div className={className}>
      <div className="flex gap-1">
        <Select value={value} onValueChange={onChange}>
          <SelectTrigger className="h-9 flex-1">
            <SelectValue placeholder={placeholder} />
          </SelectTrigger>
          <SelectContent>
            {items.length === 0 && (
              <div className="px-2 py-1.5 text-xs text-muted-foreground">
                {fonts.isLoading ? "Cargando…" : "Sin fuentes disponibles."}
              </div>
            )}
            {items.map((f) => (
              <SelectItem key={f.path} value={f.path}>
                <span className="inline-flex items-center gap-2">
                  <span>{f.name}</span>
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    {f.source}
                  </span>
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {allowUpload && (
          <>
            <input
              ref={inputRef}
              type="file"
              accept=".ttf,.otf,font/ttf,font/otf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleUpload(file);
                e.target.value = "";
              }}
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-9 w-9 shrink-0"
              onClick={() => inputRef.current?.click()}
              disabled={upload.isPending}
              title="Importar fuente (TTF/OTF)"
              aria-label="Importar fuente"
            >
              {upload.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
            </Button>
            {selected?.source === "bundled" && (
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-9 w-9 shrink-0 text-muted-foreground hover:text-destructive"
                onClick={handleDelete}
                disabled={remove.isPending}
                title={`Borrar '${selected.name}'`}
                aria-label="Borrar fuente bundled"
              >
                {remove.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
