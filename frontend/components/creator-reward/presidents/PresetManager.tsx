"use client";

import { useState } from "react";
import { Loader2, Save, Star, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  useDeletePresidentsPreset,
  usePresidentsPreset,
  usePresidentsPresets,
  useSavePresidentsPreset,
} from "@/lib/queries/creator-reward/presidents";

export function PresetManager({
  config,
  onLoad,
}: {
  config: Record<string, unknown>;
  onLoad: (config: Record<string, unknown>) => void;
}) {
  const presets = usePresidentsPresets();
  const save = useSavePresidentsPreset();
  const del = useDeletePresidentsPreset();
  const [selected, setSelected] = useState<string>("");
  const [newName, setNewName] = useState("");

  const loaded = usePresidentsPreset(selected || null);

  async function handleLoad() {
    if (!selected) return;
    if (loaded.data) {
      onLoad(loaded.data.config);
      toast.success(`Preset '${selected}' cargado.`);
    }
  }

  async function handleSave() {
    if (!newName.trim()) return;
    try {
      await save.mutateAsync({ name: newName.trim(), config });
      toast.success(`Preset '${newName.trim()}' guardado.`);
      setNewName("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al guardar.");
    }
  }

  async function handleDelete() {
    if (!selected) return;
    try {
      await del.mutateAsync(selected);
      toast.success(`Preset '${selected}' borrado.`);
      setSelected("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al borrar.");
    }
  }

  async function handleSetDefault() {
    if (!selected || !loaded.data) return;
    try {
      await save.mutateAsync({ name: "__default", config: loaded.data.config });
      toast.success(`'${selected}' marcado como default. Se cargará al abrir la página.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al marcar default.");
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={selected} onValueChange={setSelected}>
          <SelectTrigger className="h-9 min-w-0 flex-1 sm:w-48 sm:flex-none">
            <SelectValue placeholder={presets.isLoading ? "Cargando…" : "Cargar preset"} />
          </SelectTrigger>
          <SelectContent>
            {(presets.data?.items ?? []).map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" onClick={handleLoad} disabled={!selected}>
          Cargar
        </Button>
        {selected && selected !== "__default" && (
          <>
            <Button
              size="icon"
              variant="ghost"
              className="h-9 w-9"
              onClick={handleSetDefault}
              disabled={save.isPending || !loaded.data}
              aria-label={`Marcar '${selected}' como default`}
              title={`Marcar '${selected}' como default (se carga al entrar)`}
            >
              {save.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Star className="h-4 w-4" />
              )}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="h-9 w-9"
              onClick={handleDelete}
              disabled={del.isPending}
              aria-label={`Borrar preset ${selected}`}
              title={`Borrar preset ${selected}`}
            >
              {del.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
            </Button>
          </>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Nombre nuevo preset"
          className="h-9 min-w-0 flex-1 sm:w-48 sm:flex-none"
        />
        <Button
          size="sm"
          onClick={handleSave}
          disabled={!newName.trim() || save.isPending}
        >
          {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Guardar
        </Button>
      </div>
    </div>
  );
}
