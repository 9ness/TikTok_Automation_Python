"use client";

import { Textarea } from "@/components/ui/textarea";
import type { SubsAutoWord } from "@/lib/types/creator-reward";

export function WordsEditor({
  words,
  value,
  onChange,
}: {
  words: SubsAutoWord[];
  value: string;
  onChange: (text: string) => void;
}) {
  const editedCount = value.trim().split(/\s+/).filter(Boolean).length;
  const originalCount = words.length;
  const delta = editedCount - originalCount;

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {originalCount} palabras detectadas. Edita typos / palabras incorrectas.
        Si conservas el mismo número, los timestamps se mantienen 1:1. Si
        añades o eliminas, se redistribuyen por frases naturales (separadas
        por pausas del audio) con peso por longitud — mantiene la sincronía.
      </p>
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={10}
        className="font-mono text-sm"
        aria-label="Editor de palabras"
      />
      <p className="text-xs">
        {editedCount} palabras{" "}
        {delta === 0 ? (
          <span className="text-green-600">· timestamps preservados 1:1</span>
        ) : (
          <span className="text-amber-600">
            ({delta > 0 ? `+${delta}` : delta} vs original) · se redistribuirán
            proporcionalmente
          </span>
        )}
      </p>
    </div>
  );
}
