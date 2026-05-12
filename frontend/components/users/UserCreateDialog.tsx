"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { useCreateUser } from "@/lib/queries/users";
import type { Tier } from "@/lib/types/product";

const NICHES = ["skincare", "fitness", "hogar", "tech", "moda", "otros"];
const TIERS: { value: Tier; label: string }[] = [
  { value: "standard", label: "🟢 Standard" },
  { value: "advanced", label: "🟡 Advanced" },
  { value: "pro", label: "🔴 Pro" },
  { value: "veo3_prompt_only", label: "🟣 Veo 3" },
];

export function UserCreateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const router = useRouter();
  const create = useCreateUser();
  const [username, setUsername] = useState("@");
  const [displayName, setDisplayName] = useState("");
  const [niche, setNiche] = useState("otros");
  const [tier, setTier] = useState<Tier>("standard");

  function reset() {
    setUsername("@");
    setDisplayName("");
    setNiche("otros");
    setTier("standard");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || username.trim() === "@" || !displayName.trim()) return;
    try {
      const user = await create.mutateAsync({
        username: username.trim(),
        display_name: displayName.trim(),
        niche,
        default_video_tier: tier,
      });
      toast.success(`Usuario '${user.username}' creado.`);
      onOpenChange(false);
      reset();
      router.push(
        `/tiktok-shop/users/${encodeURIComponent(user.username)}` as never,
      );
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Error inesperado al crear usuario.";
      toast.error(message);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) reset();
      }}
    >
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Nuevo usuario TikTok</DialogTitle>
            <DialogDescription>
              Cuenta afiliada que gestionas. Auto-crea estructura Drive en{" "}
              <code className="font-mono">_users/@username/</code>.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="user-username">Username (con @) *</Label>
            <Input
              id="user-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="@cuenta_skincare_es"
              required
              autoFocus
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="user-display">Display name *</Label>
            <Input
              id="user-display"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Skincare Tips España"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="user-niche">Nicho</Label>
              <Select value={niche} onValueChange={setNiche}>
                <SelectTrigger id="user-niche">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {NICHES.map((n) => (
                    <SelectItem key={n} value={n}>
                      {n}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="user-tier">Tier por defecto</Label>
              <Select value={tier} onValueChange={(v) => setTier(v as Tier)}>
                <SelectTrigger id="user-tier">
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
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={create.isPending}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={
                create.isPending ||
                !displayName.trim() ||
                !username.trim() ||
                username.trim() === "@"
              }
            >
              {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Crear
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
