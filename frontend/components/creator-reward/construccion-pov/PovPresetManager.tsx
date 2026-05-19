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
  useConstruccionPovPreset,
  useConstruccionPovPresets,
  useDeleteConstruccionPovPreset,
  useSaveConstruccionPovPreset,
} from "@/lib/queries/creator-reward/construccionPov";

/**
 * Gestor de favoritos para Construcción POV.
 *
 * - Dropdown con presets guardados (lista filtrada por namespace "pov")
 * - Botón "Cargar" → trae la config del preset y la aplica vía onLoad
 * - Botón ⭐ → marca el preset seleccionado como `__default` (se auto-
 *   cargará al entrar en la página la próxima vez)
 * - Botón 🗑 → borra el preset
 * - Input + "Guardar" → guarda la config actual con el nombre que escribas
 *
 * Mismo patrón que `frontend/components/creator-reward/presidents/PresetManager.tsx`,
 * adaptado al nicho 4. Filtra `__default` de la lista visible para que no
 * aparezca como preset "humano" cargable.
 */
export function PovPresetManager({
  config,
  onLoad,
}: {
  config: Record<string, unknown>;
  onLoad: (config: Record<string, unknown>) => void;
}) {
  const presets = useConstruccionPovPresets();
  const save = useSaveConstruccionPovPreset();
  const del = useDeleteConstruccionPovPreset();
  const [selected, setSelected] = useState<string>("");
  const [newName, setNewName] = useState("");

  const loaded = useConstruccionPovPreset(selected || null);

  const visibleItems = (presets.data?.items ?? []).filter(
    (p) => p !== "__default",
  );

  async function handleLoad() {
    if (!selected || !loaded.data) return;
    onLoad(loaded.data.config);
    toast.success(`Preset '${selected}' cargado.`);
  }

  async function handleSave() {
    const name = newName.trim();
    if (!name) return;
    if (name === "__default") {
      toast.error("Nombre reservado. Usa el botón ⭐ para marcar default.");
      return;
    }
    try {
      await save.mutateAsync({ name, config });
      toast.success(`Preset '${name}' guardado.`);
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
      toast.success(
        `'${selected}' marcado como favorito. Se cargará al abrir la página.`,
      );
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Error al marcar default.",
      );
    }
  }

  async function handleSaveCurrentAsDefault() {
    try {
      await save.mutateAsync({ name: "__default", config });
      toast.success("Config actual marcada como favorita por defecto.");
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Error al guardar default.",
      );
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={selected} onValueChange={setSelected}>
          <SelectTrigger className="h-9 min-w-0 flex-1 sm:w-48 sm:flex-none">
            <SelectValue
              placeholder={
                presets.isLoading
                  ? "Cargando…"
                  : visibleItems.length === 0
                  ? "Sin presets guardados"
                  : "Cargar preset"
              }
            />
          </SelectTrigger>
          <SelectContent>
            {visibleItems.map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          variant="outline"
          onClick={handleLoad}
          disabled={!selected || loaded.isLoading}
        >
          Cargar
        </Button>
        {selected && (
          <>
            <Button
              size="icon"
              variant="ghost"
              className="h-9 w-9"
              onClick={handleSetDefault}
              disabled={save.isPending || !loaded.data}
              aria-label={`Marcar '${selected}' como favorito por defecto`}
              title={`Marcar '${selected}' como favorito (se carga al entrar)`}
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
          placeholder="Nombre del preset (ej. 'POV oscuro')"
          className="h-9 min-w-0 flex-1 sm:w-56 sm:flex-none"
        />
        <Button
          size="sm"
          onClick={handleSave}
          disabled={!newName.trim() || save.isPending}
        >
          {save.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Guardar
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={handleSaveCurrentAsDefault}
          disabled={save.isPending}
          title="Guarda la config actual como favorita por defecto (se cargará al entrar)"
        >
          <Star className="h-4 w-4" />
          Guardar como favorita
        </Button>
      </div>
    </div>
  );
}
