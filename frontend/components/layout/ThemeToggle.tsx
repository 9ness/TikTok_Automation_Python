"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  MENU_PREFS_VACIAS,
  useGuardarMenuPrefs,
  useMenuPrefs,
} from "@/lib/queries/uiMenu";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const prefs = useMenuPrefs();
  const guardar = useGuardarMenuPrefs();

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" aria-label="Toggle theme">
        <Sun className="h-4 w-4" />
      </Button>
    );
  }

  const isDark = theme === "dark";
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Toggle theme"
      onClick={() => {
        const nuevo = isDark ? "light" : "dark";
        setTheme(nuevo);
        // Se guarda en la CUENTA, no solo en este dispositivo: el tema de
        // cada uno le sigue al móvil, al PC y a la APK.
        guardar.mutate({ ...(prefs.data ?? MENU_PREFS_VACIAS), tema: nuevo });
      }}
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}
