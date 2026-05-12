import { describe, expect, it, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { PhotoManager } from "@/components/products/PhotoManager";
import { mockFetch, makeProduct, renderWithProviders } from "../helpers";

const fetchMock = mockFetch();

beforeEach(() => fetchMock.reset());

describe("PhotoManager", () => {
  it("sube una foto source con multipart al endpoint correcto", async () => {
    const product = makeProduct({ id: "p_photos" });
    fetchMock.on("POST", "/api/v1/products/p_photos/photos", async () =>
      new Response(
        JSON.stringify({
          id: "amazon.jpg",
          location: "source",
          filename: "amazon.jpg",
          local_path: "/tmp/amazon.jpg",
          drive_file_id: null,
          type: null,
          preferred_for_tiers: [],
          origin: "internet",
          url_origin: null,
          added_at: "2026-05-09T10:00:00+00:00",
          generation_prompt_used: null,
          generated_at: null,
          deleted: false,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );

    // GET /products/{id} se invalida tras subir; mock para evitar 500
    fetchMock.on("GET", "/api/v1/products/p_photos", () => product);

    renderWithProviders(<PhotoManager product={product as never} />);

    const inputs = document.querySelectorAll<HTMLInputElement>("input[type='file']");
    const sourceInput = inputs[0];
    expect(sourceInput).toBeDefined();

    const file = new File(["dummy"], "amazon.jpg", { type: "image/jpeg" });
    fireEvent.change(sourceInput!, { target: { files: [file] } });

    await waitFor(() => {
      const post = fetchMock.calls.find((c) => c.method === "POST");
      expect(post).toBeDefined();
      expect(post?.url).toBe("/api/v1/products/p_photos/photos");
      // FormData en mockFetch se serializa con Object.fromEntries
      const body = post?.body as Record<string, unknown>;
      expect(body.location).toBe("source");
      expect(body.origin).toBe("internet");
    });
  });

  it("muestra empty state cuando no hay fotos source", () => {
    const product = makeProduct({ id: "p_empty" });
    renderWithProviders(<PhotoManager product={product as never} />);

    const empties = screen.getAllByText(/Sin fotos\./i);
    // Una para source, otra para generated
    expect(empties.length).toBeGreaterThanOrEqual(2);
  });
});
