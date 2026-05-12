"use client";

import { VideoModal } from "@/components/ui/video-modal";
import { api } from "@/lib/api";
import type { ActiveJob } from "@/lib/types/queue";

export function JobVideoDialog({
  job,
  open,
  onOpenChange,
}: {
  job: ActiveJob | null;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  if (!job) return null;
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const qs = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : "";
  const hasFile = !!job.result_path;
  const filename = job.result_path?.split(/[/\\]/).pop() ?? `${job.job_id}.mp4`;

  return (
    <VideoModal
      open={open}
      onOpenChange={onOpenChange}
      title={job.title || job.job_id}
      filename={filename}
      videoUrl={hasFile ? `${api.baseUrl}/api/v1/queue/${job.job_id}/video${qs}` : null}
      downloadUrl={
        hasFile ? `${api.baseUrl}/api/v1/queue/${job.job_id}/download${qs}` : null
      }
      localPath={job.result_path ?? null}
      placeholderMessage={
        job.status === "failed"
          ? "Job fallido — sin vídeo disponible."
          : `Estado: ${job.status}`
      }
    />
  );
}
