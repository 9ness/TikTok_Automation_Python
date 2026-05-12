import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import SettingsPage from "@/app/settings/page";
import { mockFetch, renderWithProviders } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("Settings — Test connection", () => {
  it("ejecuta GET /api/health y muestra el resultado", async () => {
    fetchMock.on("GET", "/api/health", () => ({
      status: "ok",
      version: "0.1.0",
      redis_configured: true,
    }));

    renderWithProviders(<SettingsPage />);

    fireEvent.click(screen.getByRole("button", { name: /Test connection/i }));

    await waitFor(() => {
      expect(screen.getByText(/v0\.1\.0/)).toBeInTheDocument();
    });
    const get = fetchMock.calls.find((c) => c.method === "GET" && c.url === "/api/health");
    expect(get).toBeDefined();
  });
});
