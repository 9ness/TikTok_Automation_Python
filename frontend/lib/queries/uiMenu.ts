"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** Cómo tiene cada persona su menú lateral: qué esconde y en qué orden.
 *
 *  Solo se guardan CLAVES (el `href` de un item, el `basePath` de un grupo),
 *  nunca el menú entero: los items los define `Sidebar.tsx` y una copia en
 *  Redis se quedaría vieja en cuanto se añada un nicho.
 */
export interface MenuPrefs {
  ocultos: string[];
  orden_grupos: string[];
  orden_items: Record<string, string[]>;
}

export const MENU_PREFS_VACIAS: MenuPrefs = {
  ocultos: [],
  orden_grupos: [],
  orden_items: {},
};

export function useMenuPrefs() {
  return useQuery<MenuPrefs>({
    queryKey: ["ui", "menu"],
    queryFn: async () => {
      const r = await api.get<MenuPrefs>(`/api/v1/ui/menu`);
      // El backend degrada a vacío si Redis no está; que los campos existan
      // siempre ahorra un `?? []` en cada uso.
      return { ...MENU_PREFS_VACIAS, ...(r ?? {}) };
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function useGuardarMenuPrefs() {
  const qc = useQueryClient();
  return useMutation<MenuPrefs, Error, MenuPrefs>({
    mutationFn: (prefs) => api.put<MenuPrefs>(`/api/v1/ui/menu`, prefs),
    // Se pinta ya: la sidebar es lo que estás mirando mientras lo tocas, y
    // esperar al PUT para ver el cambio hace pensar que no ha funcionado.
    onMutate: (prefs) => {
      qc.setQueryData(["ui", "menu"], prefs);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["ui", "menu"] });
    },
  });
}
