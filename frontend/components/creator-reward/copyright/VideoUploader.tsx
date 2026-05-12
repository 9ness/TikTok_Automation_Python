"use client";

import { Film, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";

const ACCEPTED = ["video/mp4", "video/quicktime"];

export function VideoUploader({
  file,
  onChange,
  onError,
}: {
  file: File | null;
  onChange: (file: File | null) => void;
  onError?: (msg: string) => void;
}) {
  function handleSelect(f: File | null) {
    if (!f) {
      onChange(null);
      return;
    }
    if (!ACCEPTED.includes(f.type) && !/\.(mp4|mov)$/i.test(f.name)) {
      onError?.("Formato no soportado. Solo MP4 / MOV.");
      return;
    }
    onChange(f);
  }

  if (file) {
    return (
      <div className="flex items-center gap-3 rounded-md border bg-card/50 p-4">
        <Film className="h-6 w-6 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{file.name}</p>
          <p className="text-xs text-muted-foreground">
            {(file.size / 1024 / 1024).toFixed(1)} MB
          </p>
        </div>
        <Button
          size="icon"
          variant="ghost"
          onClick={() => onChange(null)}
          aria-label="Quitar archivo"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <label
      htmlFor="copyright-upload"
      className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed py-12 text-sm text-muted-foreground transition-colors hover:bg-accent"
    >
      <Upload className="h-6 w-6" />
      <span>Click para subir vídeo (MP4 / MOV)</span>
      <input
        id="copyright-upload"
        type="file"
        accept="video/mp4,video/quicktime,.mp4,.mov"
        className="sr-only"
        onChange={(e) => handleSelect(e.target.files?.[0] ?? null)}
      />
    </label>
  );
}
