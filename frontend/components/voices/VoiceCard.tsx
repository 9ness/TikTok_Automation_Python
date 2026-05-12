"use client";

import { Mic, Star } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { Voice } from "@/lib/types/voice";

export function VoiceCard({ voice }: { voice: Voice }) {
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="rounded-full bg-secondary p-2">
              <Mic className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h3 className="truncate font-semibold">{voice.name}</h3>
              <p className="truncate font-mono text-xs text-muted-foreground">
                {voice.minimax_voice_id}
              </p>
            </div>
          </div>
          {voice.is_preset && (
            <Badge variant="outline" className="gap-1">
              <Star className="h-3 w-3" /> Preset
            </Badge>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1 text-xs">
          <Badge variant="secondary">{voice.language}</Badge>
          {voice.tags.map((t) => (
            <Badge key={t} variant="outline">
              {t}
            </Badge>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
