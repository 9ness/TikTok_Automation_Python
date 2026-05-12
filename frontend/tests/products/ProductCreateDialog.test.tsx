import { describe, expect, it, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { ProductCreateDialog } from "@/components/products/ProductCreateDialog";
import { mockFetch, makeProduct, renderWithProviders } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("ProductCreateDialog", () => {
  it("crea un producto con los campos requeridos y llama a POST /products", async () => {
    const created = makeProduct({ id: "p_new", name: "Mi producto" });
    fetchMock.on("POST", "/api/v1/products", () =>
      new Response(JSON.stringify(created), { status: 201, headers: { "Content-Type": "application/json" } }),
    );

    renderWithProviders(<ProductCreateDialog open={true} onOpenChange={() => {}} />);

    const nameInput = screen.getByLabelText(/Nombre/i);
    fireEvent.change(nameInput, { target: { value: "Mi producto" } });

    const submit = screen.getByRole("button", { name: /^Crear$/ });
    fireEvent.click(submit);

    await waitFor(() => {
      const post = fetchMock.calls.find((c) => c.method === "POST");
      expect(post).toBeDefined();
      expect(post?.url).toBe("/api/v1/products");
      expect(post?.body).toMatchObject({ name: "Mi producto", default_tier: "standard" });
    });
  });

  it("no envía request si el nombre está vacío (botón deshabilitado)", async () => {
    renderWithProviders(<ProductCreateDialog open={true} onOpenChange={() => {}} />);

    const submit = screen.getByRole("button", { name: /^Crear$/ });
    expect(submit).toBeDisabled();

    fireEvent.click(submit);
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock.calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });
});
