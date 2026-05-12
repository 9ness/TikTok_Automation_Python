import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import {
  PresidentsBatchEditor,
  emptyItem,
} from "@/components/creator-reward/presidents/PresidentsBatchEditor";
import type { PresidentsItem } from "@/lib/types/creator-reward";

let onChange: ReturnType<typeof vi.fn>;

beforeEach(() => {
  onChange = vi.fn();
});

describe("PresidentsBatchEditor", () => {
  it("añade un nuevo item al hacer click en 'Añadir vídeo'", () => {
    const items: PresidentsItem[] = [emptyItem()];
    render(<PresidentsBatchEditor items={items} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: /Añadir vídeo/i }));

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0]?.[0] as PresidentsItem[];
    expect(next).toHaveLength(2);
  });

  it("elimina un item al hacer click en su botón de quitar", () => {
    const items: PresidentsItem[] = [emptyItem(), emptyItem()];
    render(<PresidentsBatchEditor items={items} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: /Quitar vídeo 2/i }));

    const next = onChange.mock.calls[0]?.[0] as PresidentsItem[];
    expect(next).toHaveLength(1);
  });
});
