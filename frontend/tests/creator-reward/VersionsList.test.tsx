import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { VersionsList } from "@/components/creator-reward/pronosticos/VersionsList";
import type { PronosticosVersionItem } from "@/lib/types/creator-reward";

const versions: PronosticosVersionItem[] = [
  {
    id: "1",
    trigger: "cron",
    mode: "single_match",
    word_count: 120,
    estimated_duration_s: 60,
    picks_count: 5,
    script: "Hoy es el partido del siglo...",
    title: "Title v1",
    competition_focus: null,
    is_selected: true,
  },
  {
    id: "2",
    trigger: "manual",
    mode: "multi_match",
    word_count: 180,
    estimated_duration_s: 90,
    picks_count: 8,
    script: "Multi pick...",
    title: "Title v2",
    competition_focus: null,
    is_selected: false,
  },
];

let onToggle: ReturnType<typeof vi.fn>;
let onScriptChange: ReturnType<typeof vi.fn>;

beforeEach(() => {
  onToggle = vi.fn();
  onScriptChange = vi.fn();
});

describe("VersionsList", () => {
  it("dispara onToggle al click en el checkbox de una versión", () => {
    render(
      <VersionsList
        versions={versions}
        selectedIds={new Set()}
        onToggle={onToggle}
        scriptOverrides={{}}
        onScriptChange={onScriptChange}
      />,
    );

    fireEvent.click(screen.getByLabelText(/Seleccionar versión 2/i));
    expect(onToggle).toHaveBeenCalledWith("2");
  });

  it("muestra empty state cuando no hay versiones", () => {
    render(
      <VersionsList
        versions={[]}
        selectedIds={new Set()}
        onToggle={onToggle}
        scriptOverrides={{}}
        onScriptChange={onScriptChange}
      />,
    );
    expect(screen.getByText(/Sin versiones disponibles/i)).toBeInTheDocument();
  });
});
