"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Loader2, Save, Trash2 } from "lucide-react";
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
  type ShopPresetKind,
  useDeleteShopPreset,
  useSaveShopPreset,
  useShopPreset,
  useShopPresets,
} from "@/lib/queries/shopPresets";

interface PresetControlsProps {
  userId: string;
  productId: string;
  kind: ShopPresetKind;
  /** Preset cargado actualmente — controla el selector. */
  selectedName: string;
  onSelectName: (name: string) => void;
  /** Config actual del panel. Se compara contra el preset cargado para
   *  mostrar el banner de "cambios sin guardar". */
  currentConfig: Record<string, unknown>;
  /** Callback cuando el usuario carga un preset (devuelve la config). */
  onLoadConfig: (cfg: Record<string, unknown>) => void;
}

/**
 * Subcomponente compartido por las 3 cards: selector de preset + acciones
 * de guardar / borrar / sobrescribir. Patrón clonado de PovPresetManager
 * (Construcción POV) adaptado a la matriz user×product×kind.
 */
export function PresetControls({
  userId,
  productId,
  kind,
  selectedName,
  onSelectName,
  currentConfig,
  onLoadConfig,
}: PresetControlsProps) {
  const presets = useShopPresets(userId, productId, kind);
  const save = useSaveShopPreset(userId, productId, kind);
  const del = useDeleteShopPreset(userId, productId, kind);
  const loaded = useShopPreset(userId, productId, kind, selectedName || null);
  const [newName, setNewName] = useState("");

  const items = presets.data?.items ?? [];

  const hasUnsavedChanges = useMemo(() => {
    if (!selectedName || !loaded.data) return false;
    try {
      return JSON.stringify(loaded.data.config) !== JSON.stringify(currentConfig);
    } catch {
      return false;
    }
  }, [selectedName, loaded.data, currentConfig]);

  function handleLoad(name: string) {
    onSelectName(name);
    // El useQuery dispara y cuando llega la data, el efecto de abajo
    // propaga la config al panel padre.
  }

  // Auto-aplicar config cuando el preset cargado cambie.
  useEffect(() => {
    if (loaded.data && loaded.data.name === selectedName) {
      onLoadConfig(loaded.data.config);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded.data?.name]);

  async function handleSaveNew() {
    const name = newName.trim();
    if (!name) return;
    if (name === "__default") {
      toast.error("Nombre reservado. Usa el botón ⭐ tras seleccionar un preset.");
      return;
    }
    try {
      await save.mutateAsync({ name, config: currentConfig });
      toast.success(`Preset '${name}' guardado.`);
      setNewName("");
      onSelectName(name);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al guardar.");
    }
  }

  async function handleSaveDefault() {
    try {
      await save.mutateAsync({ name: "__default", config: currentConfig });
      toast.success("Config actual marcada como favorita (se autocarga al volver).");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al guardar default.");
    }
  }

  async function handleOverwrite() {
    if (!selectedName) return;
    try {
      await save.mutateAsync({ name: selectedName, config: currentConfig });
      toast.success(`Preset '${selectedName}' actualizado.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al actualizar.");
    }
  }

  async function handleDelete() {
    if (!selectedName) return;
    try {
      await del.mutateAsync(selectedName);
      toast.success(`Preset '${selectedName}' borrado.`);
      onSelectName("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error al borrar.");
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={selectedName} onValueChange={handleLoad}>
          <SelectTrigger className="h-9 min-w-0 flex-1 sm:w-56 sm:flex-none">
            <SelectValue
              placeholder={
                presets.isLoading
                  ? "Cargando…"
                  : items.length === 0
                    ? "Sin presets — configura abajo"
                    : "Cargar preset"
              }
            />
          </SelectTrigger>
          <SelectContent>
            {items.map((p) => (
              <SelectItem key={p} value={p}>
                {p === "__default" ? "⭐ Por defecto" : p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {selectedName && (
          <Button
            size="icon"
            variant="ghost"
            className="h-9 w-9"
            onClick={handleDelete}
            disabled={del.isPending}
            aria-label={`Borrar preset ${selectedName}`}
            title={`Borrar preset ${selectedName}`}
          >
            {del.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Guardar config actual como…"
          className="h-9 min-w-0 flex-1 sm:w-56 sm:flex-none"
        />
        <Button
          size="sm"
          onClick={handleSaveNew}
          disabled={!newName.trim() || save.isPending}
        >
          {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Guardar nuevo
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={handleSaveDefault}
          disabled={save.isPending}
          title="Marca esta config como la default (se autocarga al volver)"
        >
          ⭐ Como favorita
        </Button>
      </div>

      {selectedName && hasUnsavedChanges && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2">
          <p className="text-xs text-amber-200">
            Has modificado <b>'{selectedName}'</b> — cambios sin guardar.
          </p>
          <Button size="sm" onClick={handleOverwrite} disabled={save.isPending}>
            {save.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="h-4 w-4" />
            )}
            Guardar en '{selectedName}'
          </Button>
        </div>
      )}
    </div>
  );
}
