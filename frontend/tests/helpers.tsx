/**
 * Helpers compartidos por los tests del frontend.
 *
 * - `renderWithProviders`: monta un QueryClientProvider fresco por test
 *   (sin retries, gcTime=0) + ThemeProvider stub. NO incluye Toaster
 *   porque sonner intenta portales animados que generan ruido en jsdom.
 * - `mockApi`: stub global de `fetch` por endpoint. Cada test registra
 *   las rutas que necesita y mockApi devuelve el handler matching.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  const client = makeQueryClient();
  function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return { client, ...render(ui, { wrapper: Wrapper, ...options }) };
}

// ---------------------------------------------------------------------------
// Mock fetch
// ---------------------------------------------------------------------------

export type Handler = (req: Request) => unknown | Promise<unknown>;

export interface MockedFetch {
  on: (method: string, path: string, handler: Handler) => void;
  reset: () => void;
  calls: { method: string; url: string; body: unknown }[];
}

export function mockFetch(): MockedFetch {
  const handlers = new Map<string, Handler>();
  const calls: MockedFetch["calls"] = [];

  const fetchSpy = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const req = new Request(url instanceof Request ? url : url.toString(), init);
    const method = (init?.method ?? req.method ?? "GET").toUpperCase();
    const u = new URL(req.url);
    const key = `${method} ${u.pathname}`;

    let body: unknown = undefined;
    if (init?.body) {
      if (init.body instanceof FormData) {
        body = Object.fromEntries(init.body.entries());
      } else if (typeof init.body === "string") {
        try {
          body = JSON.parse(init.body);
        } catch {
          body = init.body;
        }
      }
    }
    calls.push({ method, url: u.pathname + u.search, body });

    const handler = handlers.get(key);
    if (!handler) {
      return new Response(
        JSON.stringify({ error: `No mock for ${key}`, code: "no_mock", details: {} }),
        { status: 500, headers: { "Content-Type": "application/json" } },
      );
    }
    const result = await handler(req);
    if (result instanceof Response) return result;
    return new Response(JSON.stringify(result), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  vi.stubGlobal("fetch", fetchSpy);

  return {
    on: (method, path, handler) => {
      handlers.set(`${method.toUpperCase()} ${path}`, handler);
    },
    reset: () => {
      handlers.clear();
      calls.length = 0;
      fetchSpy.mockClear();
    },
    calls,
  };
}

// ---------------------------------------------------------------------------
// Sample fixtures
// ---------------------------------------------------------------------------

export function makeProduct(overrides: Partial<Record<string, unknown>> = {}) {
  const base = {
    id: "p_test",
    slug: "test_product",
    name: "Test Product",
    brand: "TestBrand",
    category: "fitness",
    subcategory: null,
    target_audience: [],
    key_features: [],
    selling_points: [],
    tiktok_shop: { product_url: null, product_id: null, commission_rate: 0.1, price_eur: null },
    photos: { source: [], generated: [] },
    video_config: {
      default_tier: "standard",
      default_duration: 15,
      default_resolution: "720p",
      preferred_styles: ["asmr_macro"],
      voice_preference: { type: "tts_preset", voice_id: null, tone: "energetic" },
      has_complex_packaging: false,
      use_first_frame_anchor: true,
    },
    hooks_library: [],
    performance_history: {
      total_videos_generated: 0,
      total_orders_generated: 0,
      best_hook_category: null,
      promoted_to_advanced_at: null,
      promoted_to_pro_at: null,
    },
    needs_nano_banana_regeneration: false,
    drive_folder: "/tmp/test_product",
    deleted: false,
    last_analyzed_at: null,
    created_at: "2026-05-09T10:00:00+00:00",
    updated_at: "2026-05-09T10:00:00+00:00",
  };
  return { ...base, ...overrides };
}

export function makeUser(overrides: Partial<Record<string, unknown>> = {}) {
  const base = {
    id: "u_test",
    username: "@test_user",
    display_name: "Test User",
    niche: "fitness",
    language: "es",
    country: "ES",
    status: "pilot",
    followers_count: 1200,
    creator_health_rating: 200,
    pilot_program: {
      started_at: "2026-04-01T00:00:00+00:00",
      shoppable_videos_published: 0,
      orders_generated: 0,
      quiz_passed: false,
      graduation_eligible: false,
      weekly_shoppable_remaining: 5,
      weekly_shoppable_reset_at: "2026-05-13",
    },
    drive_folder: "/tmp/_users/@test_user",
    assigned_products: [],
    default_voice_id: null,
    default_language: "es",
    default_video_tier: "standard",
    deleted: false,
    created_at: "2026-05-09T10:00:00+00:00",
    updated_at: "2026-05-09T10:00:00+00:00",
  };
  return { ...base, ...overrides };
}

export function makePilotProgress(overrides: Partial<Record<string, unknown>> = {}) {
  const base = {
    username: "@test_user",
    status: "pilot",
    days_in_program: 10,
    shoppable_videos_count: 2,
    current_chr: 200,
    orders_count: 0,
    followers: 1200,
    weekly_shoppable_used: 1,
    weekly_shoppable_remaining: 4,
    weekly_reset_at: "2026-05-13",
    quiz_passed: false,
    graduation_status: "not_eligible",
    days_until_eligible: null,
    requirements_met: [
      {
        name: "via_a_5000_followers",
        label: "Vía A: ≥5000 followers",
        met: false,
        missing: ["Necesitas 3800 followers más (actual: 1200)."],
      },
      {
        name: "via_b_videos_quiz_chr",
        label: "Vía B: ≥6 shoppable + ≥30d + quiz + CHR≥176",
        met: false,
        missing: ["Faltan 4 vídeos shoppable.", "Quiz pendiente."],
      },
      {
        name: "via_c_orders_30d",
        label: "Vía C: ≥10 órdenes + ≥30d",
        met: false,
        missing: ["Faltan 10 órdenes shoppable.", "Faltan 20 días en el programa."],
      },
    ],
  };
  return { ...base, ...overrides };
}
