"use client";

import { VideoModal } from "@/components/ui/video-modal";
import { api } from "@/lib/api";
import type { GenerationResponse } from "@/lib/types/generation";

export function VideoPlayer({
  generation,
  open,
  onOpenChange,
}: {
  generation: GenerationResponse | null;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  if (!generation) return null;
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const qs = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : "";
  const isCompleted = generation.generation_status === "completed";
  const hasFile = isCompleted && !!generation.local_path;
  const filename =
    generation.local_path?.split(/[/\\]/).pop() ?? `gen_${generation.id}.mp4`;

  return (
    <VideoModal
      open={open}
      onOpenChange={onOpenChange}
      title={`Vídeo ${generation.id.slice(0, 8)}`}
      filename={filename}
      videoUrl={
        hasFile ? `${api.baseUrl}/api/v1/generations/${generation.id}/video${qs}` : null
      }
      downloadUrl={
        hasFile ? `${api.baseUrl}/api/v1/generations/${generation.id}/video${qs}` : null
      }
      localPath={generation.local_path ?? null}
      placeholderMessage={
        generation.generation_status === "failed"
          ? "Generación fallida — sin vídeo disponible."
          : `Estado: ${generation.generation_status}`
      }
    />
  );
}
