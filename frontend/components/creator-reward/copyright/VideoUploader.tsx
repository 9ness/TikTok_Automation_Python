"use client";

import { Film, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";

const ACCEPTED = ["video/mp4", "video/quicktime"];

function isValid(f: File) {
  return ACCEPTED.includes(f.type) || /\.(mp4|mov)$/i.test(f.name);
}

const fileKey = (f: File) => `${f.name}:${f.size}:${f.lastModified}`;

export function VideoUploader({
  files,
  onChange,
  onError,
  multiple = true,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  onError?: (msg: string) => void;
  multiple?: boolean;
}) {
  function handleSelect(selected: FileList | null) {
    if (!selected || selected.length === 0) return;
    const incoming = Array.from(selected);
    const rejected = incoming.filter((f) => !isValid(f));
    if (rejected.length) {
      onError?.("Formato no soportado. Solo MP4 / MOV.");
    }
    const valid = incoming.filter(isValid);
    if (!valid.length) return;
    if (!multiple) {
      // Modo single: el nuevo archivo reemplaza al anterior.
      onChange([valid[0]!]);
      return;
    }
    // Dedupe contra los ya seleccionados (mismo nombre+tamaño+fecha).
    const existing = new Set(files.map(fileKey));
    const merged = [...files, ...valid.filter((f) => !existing.has(fileKey(f)))];
    onChange(merged);
  }

  function removeAt(idx: number) {
    onChange(files.filter((_, i) => i !== idx));
  }

  return (
    <div className="space-y-2">
      {files.length > 0 && (
        <div className="space-y-2">
          {multiple && (
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground">
                {files.length} vídeo{files.length > 1 ? "s" : ""} · se encolan uno a uno
              </p>
              <button
                type="button"
                onClick={() => onChange([])}
                className="text-xs text-muted-foreground underline-offset-2 hover:underline"
              >
                Quitar todos
              </button>
            </div>
          )}
          <ul className="space-y-2">
            {files.map((file, idx) => (
              <li
                key={fileKey(file)}
                className="flex items-center gap-3 rounded-md border bg-card/50 p-3"
              >
                <Film className="h-5 w-5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{file.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(file.size / 1024 / 1024).toFixed(1)} MB
                  </p>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => removeAt(idx)}
                  aria-label={`Quitar ${file.name}`}
                >
                  <X className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <label
        htmlFor="copyright-upload"
        className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed py-8 text-sm text-muted-foreground transition-colors hover:bg-accent"
      >
        <Upload className="h-6 w-6" />
        <span>
          {files.length === 0
            ? multiple
              ? "Click para subir vídeos (MP4 / MOV)"
              : "Click para subir vídeo (MP4 / MOV)"
            : multiple
              ? "Añadir más vídeos (MP4 / MOV)"
              : "Cambiar vídeo (MP4 / MOV)"}
        </span>
        <input
          id="copyright-upload"
          type="file"
          accept="video/mp4,video/quicktime,.mp4,.mov"
          multiple={multiple}
          className="sr-only"
          onChange={(e) => {
            handleSelect(e.target.files);
            // Reset para poder volver a seleccionar el mismo archivo.
            e.target.value = "";
          }}
        />
      </label>
    </div>
  );
}
