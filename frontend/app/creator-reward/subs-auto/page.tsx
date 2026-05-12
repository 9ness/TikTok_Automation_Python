"use client";

import { useState } from "react";
import { Check, ChevronLeft, ChevronRight, Loader2, Send } from "lucide-react";
import { toast } from "sonner";

import { VideoUploader } from "@/components/creator-reward/copyright/VideoUploader";
import { SubsAutoStyleEditor } from "@/components/creator-reward/subs-auto/SubsAutoStyleEditor";
import { WordsEditor } from "@/components/creator-reward/subs-auto/WordsEditor";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  useEnqueueSubsAuto,
  useTranscribe,
} from "@/lib/queries/creator-reward/subsAuto";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type {
  SubsAutoStyleConfig,
  SubsAutoTranscribeResponse,
} from "@/lib/types/creator-reward";
import { cn } from "@/lib/utils";

const MODELS = ["tiny", "small", "medium", "large"];
const QUALITIES = [
  "1080p (Lento)",
  "720p (Medio)",
  "480p (Rápido)",
  "240p (Ultra Rápido)",
];

const DEFAULT_STYLE: SubsAutoStyleConfig = {
  font_path: "C:\\Windows\\Fonts\\impact.ttf",
  highlight_mode: "pill",
  highlight_color: "#BB0808",
  text_color: "#FFFFFF",
  stroke_color: "#000000",
  stroke_width: 3,
  case_mode: "UPPERCASE",
  font_scale: 0.045,
  max_words: 3,
  y_position: 0.78,
  pill_enabled: true,
  max_width: 0.85,
  sync_offset: 0,
};

const STEPS = ["Subir vídeo", "Editar palabras", "Estilo + Encolar"] as const;

export default function SubsAutoPage() {
  const transcribe = useTranscribe();
  const enqueue = useEnqueueSubsAuto();
  const openQueue = useDrawerStore((s) => s.openQueue);

  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [file, setFile] = useState<File | null>(null);
  const [modelSize, setModelSize] = useState("small");
  const [language, setLanguage] = useState("");
  const [audioType, setAudioType] = useState("speech");
  const [quality, setQuality] = useState("720p (Medio)");
  const [transcript, setTranscript] = useState<SubsAutoTranscribeResponse | null>(null);
  const [editedText, setEditedText] = useState("");
  const [style, setStyle] = useState<SubsAutoStyleConfig>(DEFAULT_STYLE);
  const [transcribeProgress, setTranscribeProgress] = useState<{
    frac: number;
    msg: string;
  } | null>(null);

  async function handleTranscribe() {
    if (!file) return;
    setTranscribeProgress({ frac: 0, msg: "⏳ Iniciando…" });
    try {
      const res = await transcribe.mutateAsync({
        file,
        model_size: modelSize,
        language: language || null,
        audio_type: audioType,
        onProgress: (frac, msg) => setTranscribeProgress({ frac, msg }),
      });
      setTranscript(res);
      setEditedText(res.words.map((w) => w.word).join(" "));
      setStep(1);
      toast.success(`${res.words.length} palabras transcritas.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Error al transcribir.");
    } finally {
      setTranscribeProgress(null);
    }
  }

  async function submit() {
    if (!transcript) return;
    try {
      const res = await enqueue.mutateAsync({
        input_path: transcript.input_path_relative,
        out_path: transcript.out_path_relative,
        edited_text: editedText.trim() || null,
        model_size: modelSize,
        language: language || null,
        audio_type: audioType,
        quality_label: quality,
        style,
      });
      toast.success(`Encolado · job ${res.job_id.slice(0, 8)}`);
      openQueue();
      // reset
      setStep(0);
      setFile(null);
      setTranscript(null);
      setEditedText("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al encolar.");
    }
  }

  return (
    <div className="container mx-auto space-y-6 p-6 md:p-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Subs sobre Vídeo</h1>
        <p className="text-sm text-muted-foreground">
          Whisper transcribe → editas palabras → render con karaoke overlay.
        </p>
      </header>

      <ol className="flex flex-wrap items-center gap-2">
        {STEPS.map((label, i) => {
          const done = i < step;
          const active = i === step;
          return (
            <li key={label} className="flex items-center gap-2">
              <div
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold",
                  done && "bg-primary text-primary-foreground",
                  active && "border-2 border-primary text-primary",
                  !done && !active && "bg-muted text-muted-foreground",
                )}
              >
                {done ? <Check className="h-4 w-4" /> : i + 1}
              </div>
              <span
                className={cn(
                  "text-xs",
                  active ? "font-semibold" : "text-muted-foreground",
                )}
              >
                {label}
              </span>
            </li>
          );
        })}
      </ol>

      <Card>
        <CardContent className="space-y-4 p-6">
          {step === 0 && (
            <>
              <VideoUploader
                file={file}
                onChange={setFile}
                onError={(msg) => toast.error(msg)}
              />
              <div className="grid gap-3 md:grid-cols-3">
                <Field label="Modelo Whisper">
                  <Select value={modelSize} onValueChange={setModelSize}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MODELS.map((m) => (
                        <SelectItem key={m} value={m}>
                          {m}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="Idioma (opcional)">
                  <Input
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    placeholder="es / en / auto"
                  />
                </Field>
                <Field label="Tipo audio">
                  <Select value={audioType} onValueChange={setAudioType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="speech">speech</SelectItem>
                      <SelectItem value="music">music</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              </div>
              <Button
                onClick={handleTranscribe}
                disabled={!file || transcribe.isPending}
                className="w-full"
              >
                {transcribe.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Transcribir
              </Button>

              {transcribeProgress && (
                <div className="space-y-1.5">
                  <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full bg-primary transition-[width] duration-300 ease-out"
                      style={{ width: `${Math.round(transcribeProgress.frac * 100)}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate text-muted-foreground">
                      {transcribeProgress.msg}
                    </span>
                    <span className="font-mono tabular-nums">
                      {Math.round(transcribeProgress.frac * 100)}%
                    </span>
                  </div>
                </div>
              )}
            </>
          )}

          {step === 1 && transcript && (
            <WordsEditor
              words={transcript.words}
              value={editedText}
              onChange={setEditedText}
            />
          )}

          {step === 2 && transcript && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-end gap-3">
                <Field label="Calidad render">
                  <Select value={quality} onValueChange={setQuality}>
                    <SelectTrigger className="h-9 w-48">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {QUALITIES.map((q) => (
                        <SelectItem key={q} value={q}>
                          {q}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
              </div>

              <SubsAutoStyleEditor
                style={style}
                onChange={setStyle}
                inputPath={transcript.input_path_relative}
                sampleText={
                  editedText
                    ? editedText.split(/\s+/).slice(0, 8).join(" ")
                    : transcript.words
                        .slice(0, 8)
                        .map((w) => w.word)
                        .join(" ")
                }
              />
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button
          variant="outline"
          onClick={() => setStep((s) => Math.max(0, s - 1) as 0 | 1 | 2)}
          disabled={step === 0}
        >
          <ChevronLeft className="h-4 w-4" /> Anterior
        </Button>
        {step < 2 ? (
          <Button
            onClick={() => setStep((s) => Math.min(2, s + 1) as 0 | 1 | 2)}
            disabled={(step === 0 && !transcript) || (step === 1 && !editedText.trim())}
          >
            Siguiente <ChevronRight className="h-4 w-4" />
          </Button>
        ) : (
          <Button onClick={submit} disabled={enqueue.isPending}>
            {enqueue.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Encolar render
          </Button>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}
