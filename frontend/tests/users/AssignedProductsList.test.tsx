import { describe, expect, it, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { AssignedProductsList } from "@/components/users/AssignedProductsList";
import { makeProduct, makeUser, mockFetch, renderWithProviders } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("AssignedProductsList", () => {
  it("desasigna un producto vía DELETE /users/{username}/products/{id}", async () => {
    const product = makeProduct({ id: "p_assigned", name: "Producto X" });
    const user = makeUser({
      username: "@assign_user",
      assigned_products: ["p_assigned"],
    });

    fetchMock.on("GET", "/api/v1/products", () => ({
      items: [product],
      total: 1,
      limit: 200,
      offset: 0,
    }));

    fetchMock.on(
      "DELETE",
      "/api/v1/users/%40assign_user/products/p_assigned",
      () => new Response(null, { status: 204 }),
    );

    // useUser tras invalidate
    fetchMock.on(
      "GET",
      "/api/v1/users/%40assign_user",
      () => ({ ...user, assigned_products: [] }),
    );

    renderWithProviders(<AssignedProductsList user={user as never} />);

    await waitFor(() =>
      expect(screen.getByText("Producto X")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: /Desasignar Producto X/i }));

    await waitFor(() => {
      const del = fetchMock.calls.find((c) => c.method === "DELETE");
      expect(del).toBeDefined();
      expect(del?.url).toBe("/api/v1/users/%40assign_user/products/p_assigned");
    });
  });

  it("muestra empty state cuando no hay productos asignados", () => {
    const user = makeUser({ assigned_products: [] });
    fetchMock.on("GET", "/api/v1/products", () => ({
      items: [],
      total: 0,
      limit: 200,
      offset: 0,
    }));
    renderWithProviders(<AssignedProductsList user={user as never} />);
    expect(screen.getByText(/Sin productos asignados/i)).toBeInTheDocument();
  });
});
