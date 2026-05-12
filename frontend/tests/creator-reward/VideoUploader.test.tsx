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
  it("acepta MP4 y dispara onChange", () => {
    const { container } = render(
      <VideoUploader file={null} onChange={onChange} onError={onError} />,
    );
    const input = container.querySelector("input[type='file']");
    expect(input).not.toBeNull();
    const file = new File(["dummy"], "test.mp4", { type: "video/mp4" });
    fireEvent.change(input!, { target: { files: [file] } });
    expect(onChange).toHaveBeenCalledWith(file);
    expect(onError).not.toHaveBeenCalled();
  });

  it("rechaza formatos no soportados llamando a onError", () => {
    const { container } = render(
      <VideoUploader file={null} onChange={onChange} onError={onError} />,
    );
    const input = container.querySelector("input[type='file']");
    const file = new File(["dummy"], "test.txt", { type: "text/plain" });
    fireEvent.change(input!, { target: { files: [file] } });
    expect(onError).toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();
  });
});
