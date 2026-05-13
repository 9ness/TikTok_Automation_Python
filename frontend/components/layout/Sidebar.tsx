"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Captions,
  ChevronDown,
  ChevronRight,
  Crown,
  DollarSign,
  History,
  LayoutDashboard,
  Loader2,
  Menu,
  Mic,
  Package,
  Settings,
  ShieldOff,
  ShoppingBag,
  Sparkles,
  Trophy,
  Users,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { QueueBadge } from "@/components/queue/QueueBadge";
import { DiagnosticsPanel } from "@/components/layout/DiagnosticsPanel";
import { ThemeToggle } from "./ThemeToggle";
import { useLogout, useMe } from "@/lib/queries/auth";
import { useDiagnosticsSummary } from "@/lib/queries/diagnostics";
import { LogOut, User } from "lucide-react";

import type { LucideIcon } from "lucide-react";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

type NavGroup =
  | { kind: "single"; item: NavItem }
  | { kind: "group"; title: string; basePath: string; icon: LucideIcon; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    kind: "single",
    item: { href: "/", label: "Dashboard", icon: LayoutDashboard },
  },
  {
    kind: "group",
    title: "Creator Reward",
    basePath: "/creator-reward",
    icon: Trophy,
    items: [
      { href: "/creator-reward/presidents", label: "Presidentes Top 5", icon: Crown },
      { href: "/creator-reward/pronosticos", label: "Pronósticos Diarios", icon: BarChart3 },
      { href: "/creator-reward/copyright", label: "Quitar Copy", icon: ShieldOff },
      { href: "/creator-reward/subs-auto", label: "Subs sobre Vídeo", icon: Captions },
    ],
  },
  {
    kind: "group",
    title: "TikTok Shop",
    basePath: "/tiktok-shop",
    icon: ShoppingBag,
    items: [
      { href: "/tiktok-shop/products", label: "Productos", icon: Package },
      { href: "/tiktok-shop/users", label: "Usuarios", icon: Users },
      { href: "/tiktok-shop/generate", label: "Generador", icon: Sparkles },
      { href: "/tiktok-shop/history", label: "Histórico", icon: History },
      { href: "/tiktok-shop/voices", label: "Voces", icon: Mic },
    ],
  },
  {
    kind: "single",
    item: { href: "/costs", label: "Costes", icon: DollarSign },
  },
  {
    kind: "single",
    item: { href: "/settings", label: "Settings", icon: Settings },
  },
];

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  // Estado de cada grupo expandido — auto-abrir si la ruta actual cae dentro.
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const node of NAV) {
      if (node.kind === "group") init[node.title] = pathname?.startsWith(node.basePath) ?? false;
    }
    return init;
  });

  // Si cambia la ruta, asegurarse de que el grupo correspondiente sigue abierto.
  useEffect(() => {
    setExpanded((prev) => {
      const next = { ...prev };
      for (const node of NAV) {
        if (node.kind === "group" && pathname?.startsWith(node.basePath)) {
          next[node.title] = true;
        }
      }
      return next;
    });
  }, [pathname]);

  return (
    <>
      <div className="flex h-20 items-center gap-3 border-b px-5">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/brand/logo.png"
          alt="NebulabsAI"
          width={36}
          height={36}
          className="rounded-md"
        />
        <div className="leading-tight">
          <p className="brand-gradient-text text-base font-bold tracking-tight">
            NebulabsAI
          </p>
          <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            TikTok Automation
          </p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-1">
          {NAV.map((node) =>
            node.kind === "single" ? (
              <SidebarLink
                key={node.item.href}
                item={node.item}
                pathname={pathname}
                onNavigate={onNavigate}
              />
            ) : (
              <li key={node.title}>
                <button
                  type="button"
                  onClick={() =>
                    setExpanded((prev) => ({ ...prev, [node.title]: !prev[node.title] }))
                  }
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md px-3 py-2 text-xs font-semibold uppercase tracking-wider transition-colors",
                    "text-muted-foreground hover:bg-accent/40 hover:text-foreground",
                  )}
                  aria-expanded={expanded[node.title] ?? false}
                >
                  <node.icon className="h-4 w-4" strokeWidth={1.75} />
                  {node.title}
                  {expanded[node.title] ? (
                    <ChevronDown className="ml-auto h-3 w-3" strokeWidth={2} />
                  ) : (
                    <ChevronRight className="ml-auto h-3 w-3" strokeWidth={2} />
                  )}
                </button>
                {expanded[node.title] && (
                  <ul className="ml-3 mt-1 space-y-0.5 border-l pl-3">
                    {node.items.map((item) => (
                      <SidebarLink
                        key={item.href}
                        item={item}
                        pathname={pathname}
                        onNavigate={onNavigate}
                      />
                    ))}
                  </ul>
                )}
              </li>
            ),
          )}
        </ul>
      </nav>

      <div className="shrink-0 space-y-2 border-t px-3 py-3">
        <SidebarUserBadge />
        <DiagnosticsPanel />
        <div className="flex items-center justify-between px-1">
          <VersionLabel />
          <ThemeToggle />
        </div>
      </div>
    </>
  );
}

function SidebarUserBadge() {
  const me = useMe();
  const logout = useLogout();
  const username = me.data?.username;
  if (!username) return null;
  return (
    <div className="flex items-center gap-2 rounded-md bg-muted/40 px-2 py-1.5 text-xs">
      <User className="h-3.5 w-3.5 text-brand-cyan" strokeWidth={2} />
      <span className="text-muted-foreground">Conectado:</span>
      <span className="font-semibold">{username}</span>
      <button
        type="button"
        onClick={() => logout.mutate()}
        disabled={logout.isPending}
        className="ml-auto rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-destructive disabled:opacity-50"
        title="Cerrar sesión"
        aria-label="Cerrar sesión"
      >
        {logout.isPending ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <LogOut className="h-3 w-3" strokeWidth={2} />
        )}
      </button>
    </div>
  );
}

function VersionLabel() {
  // Lee la versión del endpoint /api/v1/diagnostics/summary. Fallback al
  // texto estático si la API no responde aún (primer render).
  const q = useDiagnosticsSummary();
  const v = q.data?.version || "0.1.0";
  return <span className="text-xs text-muted-foreground">v{v}</span>;
}

function SidebarLink({
  item,
  pathname,
  onNavigate,
}: {
  item: NavItem;
  pathname: string | null;
  onNavigate?: () => void;
}) {
  const active =
    item.href === "/" ? pathname === "/" : pathname?.startsWith(item.href) ?? false;
  const Icon = item.icon;
  return (
    <li>
      <Link
        href={item.href as never}
        onClick={onNavigate}
        className={cn(
          "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-200",
          active
            ? "nav-active-indicator bg-accent/70 font-medium text-accent-foreground"
            : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
        )}
      >
        <Icon
          className={cn(
            "h-4 w-4 transition-colors",
            active ? "text-brand-cyan" : "",
          )}
          strokeWidth={1.75}
        />
        {item.label}
      </Link>
    </li>
  );
}

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* Desktop: sticky a la viewport, h-screen + overflow-hidden para que
          el nav haga scroll interno y el footer (user/diagnóstico/versión)
          quede SIEMPRE abajo sin necesidad de scroll de página. */}
      <aside className="sticky top-0 hidden h-screen overflow-hidden md:flex md:w-64 md:flex-col md:border-r md:bg-card">
        <SidebarContent />
      </aside>

      {/* QueueBadge flotante en esquina superior derecha (desktop). En
          móvil ya está en la barra superior. z-40 para quedar bajo modales
          (que usan z-50) pero sobre todo el contenido. */}
      <div className="pointer-events-none fixed right-3 top-3 z-40 hidden md:block">
        <div className="pointer-events-auto rounded-md border bg-card/95 px-2 py-1 shadow-lg backdrop-blur">
          <QueueBadge />
        </div>
      </div>

      {/* Mobile trigger + drawer */}
      <div className="flex h-14 items-center justify-between border-b px-4 md:hidden">
        <div className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/brand/logo.png"
            alt="NebulabsAI"
            width={28}
            height={28}
            className="rounded"
          />
          <span className="brand-gradient-text text-sm font-bold">NebulabsAI</span>
        </div>
        <div className="flex items-center gap-1">
          <QueueBadge />
          <Button
            variant="ghost"
            size="icon"
            aria-label="Abrir menú"
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>
        </div>
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Cerrar menú"
            onClick={() => setMobileOpen(false)}
            className="absolute inset-0 bg-black/40"
          />
          <div className="absolute left-0 top-0 flex h-full w-72 flex-col bg-card shadow-lg">
            <div className="flex justify-end p-2">
              <Button
                variant="ghost"
                size="icon"
                aria-label="Cerrar menú"
                onClick={() => setMobileOpen(false)}
              >
                <X className="h-5 w-5" />
              </Button>
            </div>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}
