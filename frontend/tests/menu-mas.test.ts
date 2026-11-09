import { describe, expect, it } from "vitest";

import {
  PRINCIPAL,
  aplicarPrefs,
  navPara,
  partirMenu,
  primeraPantalla,
  type NavGroup,
} from "@/components/layout/Sidebar";
import { MENU_PREFS_VACIAS } from "@/lib/queries/uiMenu";

function claves(nav: NavGroup[]): string[] {
  return nav.map((n) => (n.kind === "single" ? n.item.href : n.basePath));
}

describe("menú con «Más» (ness)", () => {
  const base = navPara("admin", "ness");
  const todos = aplicarPrefs(base, MENU_PREFS_VACIAS);

  it("arriba solo lo que usa Néstor, en su orden, con Mis tandas suelta", () => {
    const m = partirMenu(todos, todos, PRINCIPAL.ness);
    expect(claves(m.principal)).toEqual(PRINCIPAL.ness);
    const aiPro = m.mas.find((n) => n.kind === "group" && n.basePath === "/tiktok-shop-ai-pro");
    expect(aiPro && aiPro.kind === "group" && aiPro.items.some((i) => i.href.endsWith("/mis-tandas"))).toBe(false);
    // El resto sigue vivo en «Más»: no se borra nada.
    expect(claves(m.mas)).toEqual(expect.arrayContaining(["/creator-reward", "/tiktok-shop", "/settings"]));
    expect(m.ocultos).toEqual([]);
  });

  it("lo escondido en Mi menú va a «Ocultos» y no a «Más»", () => {
    const prefs = { ...MENU_PREFS_VACIAS, ocultos: ["/tiktok-shop", "/tiktok-shop-ai-pro/cuenta-piloto"] };
    const m = partirMenu(aplicarPrefs(base, prefs), todos, PRINCIPAL.ness);
    expect(claves(m.mas)).not.toContain("/tiktok-shop");
    const ocultas = m.ocultos.flatMap((n) => (n.kind === "single" ? [n.item.href] : n.items.map((i) => i.href)));
    expect(ocultas).toContain("/tiktok-shop/radar");
    expect(ocultas).toContain("/tiktok-shop-ai-pro/cuenta-piloto");
  });

  it("al abrir la app, ness va a Mis tandas", () => {
    expect(primeraPantalla("admin", MENU_PREFS_VACIAS, "ness")).toBe("/tiktok-shop-ai-pro/mis-tandas");
  });

  it("los demás usuarios no cambian: sin «Más»", () => {
    const ana = aplicarPrefs(navPara("pro", "ana"), MENU_PREFS_VACIAS);
    const m = partirMenu(ana, ana, PRINCIPAL.ana);
    expect(m.principal).toBe(ana);
    expect(m.mas).toEqual([]);
    expect(claves(navPara("admin", "nestor2"))).not.toContain("https://panel.nebulabsmedia.com");
  });
});
