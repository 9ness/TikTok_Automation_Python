import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { HistoryFilters, type HistoryFiltersValue } from "@/components/history/HistoryFilters";

const defaultValue: HistoryFiltersValue = {
  username: "",
  productId: "",
  status: "__all__",
};

describe("HistoryFilters", () => {
  it("dispara onChange cuando el usuario escribe en el input de username", () => {
    const onChange = vi.fn();
    render(<HistoryFilters value={defaultValue} onChange={onChange} onReset={() => {}} />);

    fireEvent.change(screen.getByPlaceholderText("@user"), {
      target: { value: "@new_user" },
    });

    expect(onChange).toHaveBeenCalledWith({
      ...defaultValue,
      username: "@new_user",
    });
  });
});
