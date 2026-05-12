"use client";

import { create } from "zustand";

interface DrawerState {
  queueOpen: boolean;
  openQueue: () => void;
  closeQueue: () => void;
  toggleQueue: () => void;
}

export const useDrawerStore = create<DrawerState>((set) => ({
  queueOpen: false,
  openQueue: () => set({ queueOpen: true }),
  closeQueue: () => set({ queueOpen: false }),
  toggleQueue: () => set((s) => ({ queueOpen: !s.queueOpen })),
}));
