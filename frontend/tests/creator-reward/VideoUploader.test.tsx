import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render } from "@testing-library/react";

import { VideoUploader } from "@/components/creator-reward/copyright/VideoUploader";

let onChange: ReturnType<typeof vi.fn>;
let onError: ReturnType<typeof vi.fn>;

beforeEach(() => {
  onChange = vi.fn();
  onError = vi.fn();
});

describe("VideoUploader", () => {
  it("acepta MP4 y dispara onChange con la lista", () => {
    const { container } = render(
      <VideoUploader files={[]} onChange={onChange} onError={onError} />,
    );
    const input = container.querySelector("input[type='file']");
    expect(input).not.toBeNull();
    const file = new File(["dummy"], "test.mp4", { type: "video/mp4" });
    fireEvent.change(input!, { target: { files: [file] } });
    expect(onChange).toHaveBeenCalledWith([file]);
    expect(onError).not.toHaveBeenCalled();
  });

  it("acepta varios vídeos y los añade a los ya seleccionados", () => {
    const existing = new File(["a"], "uno.mp4", { type: "video/mp4" });
    const { container } = render(
      <VideoUploader files={[existing]} onChange={onChange} onError={onError} />,
    );
    const input = container.querySelector("input[type='file']");
    const dos = new File(["b"], "dos.mp4", { type: "video/mp4" });
    const tres = new File(["c"], "tres.mov", { type: "video/quicktime" });
    fireEvent.change(input!, { target: { files: [dos, tres] } });
    expect(onChange).toHaveBeenCalledWith([existing, dos, tres]);
    expect(onError).not.toHaveBeenCalled();
  });

  it("rechaza formatos no soportados llamando a onError", () => {
    const { container } = render(
      <VideoUploader files={[]} onChange={onChange} onError={onError} />,
    );
    const input = container.querySelector("input[type='file']");
    const file = new File(["dummy"], "test.txt", { type: "text/plain" });
    fireEvent.change(input!, { target: { files: [file] } });
    expect(onError).toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();
  });
});
