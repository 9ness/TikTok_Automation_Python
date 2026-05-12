"use client";

import { useState } from "react";
import { Loader2, RefreshCw, Settings, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import {
  useDeleteGeneration,
  useRegenerateGeneration,
} from "@/lib/queries/generations";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type { GenerationResponse } from "@/lib/types/generation";
import { RegenerateDialog } from "./RegenerateDialog";

export function VideoActions({ generation }: { generation: GenerationResponse }) {
  const regen = useRegenerateGeneration();
  const del = useDeleteGeneration();
  const openQueue = useDrawerStore((s) => s.openQueue);
  const [withChangesOpen, setWithChangesOpen] = useState(false);

  async function regenerateIdentical() {
    try {
      const res = await regen.mutateAsync({ generationId: generation.id });
      toast.success(`Encolado · job ${res.job_id.slice(0, 8)}`);
      openQueue();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error al regenerar.";
      toast.error(message);
    }
  }

  async function handleDelete() {
    try {
      await del.mutateAsync(generation.id);
      toast.success("Generación eliminada del histórico.");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error al eliminar.";
      toast.error(message);
    }
  }

  return (
    <div className="flex items-center gap-1">
      <Button
        size="sm"
        variant="ghost"
        onClick={(e) => {
          e.stopPropagation();
          regenerateIdentical();
        }}
        disabled={regen.isPending}
        aria-label="Regenerar idéntico"
      >
        {regen.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <RefreshCw className="h-4 w-4" />
        )}
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={(e) => {
          e.stopPropagation();
          setWithChangesOpen(true);
        }}
        aria-label="Regenerar con cambios"
      >
        <Settings className="h-4 w-4" />
      </Button>

      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => e.stopPropagation()}
            aria-label="Eliminar"
            disabled={del.isPending}
          >
            {del.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar generación del histórico?</AlertDialogTitle>
            <AlertDialogDescription>
              Soft-delete: el archivo MP4 sigue en disco pero no aparece en el
              histórico.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                handleDelete();
              }}
            >
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <RegenerateDialog
        generation={generation}
        open={withChangesOpen}
        onOpenChange={setWithChangesOpen}
      />
    </div>
  );
}
