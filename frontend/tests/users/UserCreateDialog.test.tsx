import { describe, expect, it, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { UserCreateDialog } from "@/components/users/UserCreateDialog";
import { makeUser, mockFetch, renderWithProviders } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("UserCreateDialog", () => {
  it("crea un usuario con username + display_name y POSTea a /api/v1/users", async () => {
    const created = makeUser({ username: "@nuevo", display_name: "Nuevo" });
    fetchMock.on(
      "POST",
      "/api/v1/users",
      () =>
        new Response(JSON.stringify(created), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
    );

    renderWithProviders(<UserCreateDialog open={true} onOpenChange={() => {}} />);

    fireEvent.change(screen.getByLabelText(/Username/i), {
      target: { value: "@nuevo" },
    });
    fireEvent.change(screen.getByLabelText(/Display name/i), {
      target: { value: "Nuevo" },
    });

    fireEvent.click(screen.getByRole("button", { name: /^Crear$/ }));

    await waitFor(() => {
      const post = fetchMock.calls.find((c) => c.method === "POST");
      expect(post).toBeDefined();
      expect(post?.url).toBe("/api/v1/users");
      expect(post?.body).toMatchObject({
        username: "@nuevo",
        display_name: "Nuevo",
      });
    });
  });

  it("no envía POST si el username solo es '@' (botón deshabilitado)", async () => {
    renderWithProviders(<UserCreateDialog open={true} onOpenChange={() => {}} />);
    // El input arranca con "@" como placeholder, sin display_name → disabled
    const submit = screen.getByRole("button", { name: /^Crear$/ });
    expect(submit).toBeDisabled();
    fireEvent.click(submit);
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock.calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });
});
