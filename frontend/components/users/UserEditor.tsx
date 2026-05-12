"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import { useUpdateUser } from "@/lib/queries/users";
import type { Tier } from "@/lib/types/product";
import type { User, UserStatus } from "@/lib/types/user";

const TIERS: { value: Tier; label: string }[] = [
  { value: "standard", label: "🟢 Standard" },
  { value: "advanced", label: "🟡 Advanced" },
  { value: "pro", label: "🔴 Pro" },
  { value: "veo3_prompt_only", label: "🟣 Veo 3" },
];

export function UserEditor({ user }: { user: User }) {
  const update = useUpdateUser(user.username);
  const [form, setForm] = useState({
    display_name: user.display_name,
    niche: user.niche,
    language: user.language,
    country: user.country,
    followers_count: user.followers_count,
    creator_health_rating: user.creator_health_rating,
    status: user.status,
    default_video_tier: user.default_video_tier,
  });

  async function save() {
    try {
      await update.mutateAsync(form);
      toast.success("Usuario actualizado.");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error al guardar.";
      toast.error(message);
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Field label="Display name">
        <Input
          value={form.display_name}
          onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
        />
      </Field>
      <Field label="Nicho">
        <Input
          value={form.niche}
          onChange={(e) => setForm((f) => ({ ...f, niche: e.target.value }))}
        />
      </Field>
      <Field label="Idioma">
        <Input
          value={form.language}
          onChange={(e) => setForm((f) => ({ ...f, language: e.target.value }))}
        />
      </Field>
      <Field label="País">
        <Input
          value={form.country}
          onChange={(e) => setForm((f) => ({ ...f, country: e.target.value }))}
        />
      </Field>
      <Field label="Followers">
        <Input
          type="number"
          min="0"
          value={form.followers_count}
          onChange={(e) =>
            setForm((f) => ({ ...f, followers_count: Number(e.target.value) }))
          }
        />
      </Field>
      <Field label="Creator Health Rating (CHR)">
        <Input
          type="number"
          min="0"
          max="300"
          value={form.creator_health_rating}
          onChange={(e) =>
            setForm((f) => ({
              ...f,
              creator_health_rating: Number(e.target.value),
            }))
          }
        />
      </Field>
      <Field label="Status">
        <Select
          value={form.status}
          onValueChange={(v) => setForm((f) => ({ ...f, status: v as UserStatus }))}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="pilot">Pilot</SelectItem>
            <SelectItem value="graduated">Graduado</SelectItem>
          </SelectContent>
        </Select>
      </Field>
      <Field label="Tier por defecto">
        <Select
          value={form.default_video_tier}
          onValueChange={(v) =>
            setForm((f) => ({ ...f, default_video_tier: v as Tier }))
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TIERS.map((t) => (
              <SelectItem key={t.value} value={t.value}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <div className="md:col-span-2">
        <Button onClick={save} disabled={update.isPending}>
          {update.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Guardar
        </Button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
