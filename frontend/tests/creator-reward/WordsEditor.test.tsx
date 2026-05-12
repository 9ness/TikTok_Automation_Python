import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { WordsEditor } from "@/components/creator-reward/subs-auto/WordsEditor";
import type { SubsAutoWord } from "@/lib/types/creator-reward";

const words: SubsAutoWord[] = [
  { word: "hola", start: 0, end: 0.5 },
  { word: "mundo", start: 0.5, end: 1 },
];

describe("WordsEditor", () => {
  it("dispara onChange al editar el texto y muestra contador", () => {
    const onChange = vi.fn();
    render(<WordsEditor words={words} value="hola mundo" onChange={onChange} />);

    fireEvent.change(screen.getByLabelText(/Editor de palabras/i), {
      target: { value: "hola querido mundo" },
    });
    expect(onChange).toHaveBeenCalledWith("hola querido mundo");
    expect(screen.getByText(/timestamps preservados 1:1/i)).toBeInTheDocument();
  });

  it("indica redistribución proporcional cuando cambia el conteo de palabras", () => {
    render(<WordsEditor words={words} value="hola querido mundo" onChange={() => {}} />);
    expect(screen.getByText(/redistribuirán proporcionalmente/i)).toBeInTheDocument();
  });
});
