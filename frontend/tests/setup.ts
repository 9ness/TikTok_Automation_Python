import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/tiktok-shop/products",
  useSearchParams: () => new URLSearchParams(),
  redirect: vi.fn(),
}));

// jsdom no implementa estos APIs que Radix usa internamente.
if (typeof window !== "undefined") {
  // matchMedia stub
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }),
    });
  }

  // ResizeObserver stub (Radix Select)
  if (typeof window.ResizeObserver === "undefined") {
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as never;
  }

  // PointerEvent shims (Radix uses pointer capture)
  if (typeof window.HTMLElement.prototype.scrollIntoView === "undefined") {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
  }
  if (typeof window.HTMLElement.prototype.hasPointerCapture === "undefined") {
    window.HTMLElement.prototype.hasPointerCapture = vi.fn();
  }
  if (typeof window.HTMLElement.prototype.releasePointerCapture === "undefined") {
    window.HTMLElement.prototype.releasePointerCapture = vi.fn();
  }
}
