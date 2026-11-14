import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResizeHandle, usePanelWidth } from "@/components/ResizeHandle";

// jsdom has no PointerEvent; a MouseEvent subclass carries clientX like a browser would.
if (!("PointerEvent" in window)) {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
    }
  }
  Object.assign(window, { PointerEvent: PointerEventPolyfill });
}

function Harness() {
  const panel = usePanelWidth("test.panel", 380, 300, () => 700);
  return (
    <>
      <ResizeHandle width={panel.width} onResize={panel.setWidth} onReset={panel.reset} min={300} max={700} />
      <output data-testid="w">{panel.width}</output>
    </>
  );
}

describe("ResizeHandle", () => {
  it("resizes by keyboard and drag, clamps, remembers and resets", () => {
    localStorage.removeItem("test.panel");
    render(<Harness />);
    const handle = screen.getByRole("separator");
    const width = () => Number(screen.getByTestId("w").textContent);
    expect(width()).toBe(380);

    fireEvent.keyDown(handle, { key: "ArrowLeft" }); // wider panel
    expect(width()).toBe(404);
    fireEvent.keyDown(handle, { key: "Home" });
    expect(width()).toBe(700);
    fireEvent.keyDown(handle, { key: "End" });
    expect(width()).toBe(300);

    // Drag 150 px to the left: the right-hand panel grows by 150 px.
    fireEvent.pointerDown(handle, { clientX: 500, pointerId: 1 });
    fireEvent.pointerMove(handle, { clientX: 350, pointerId: 1 });
    fireEvent.pointerUp(handle, { clientX: 350, pointerId: 1 });
    expect(width()).toBe(450);
    expect(localStorage.getItem("test.panel")).toBe("450");

    fireEvent.doubleClick(handle);
    expect(width()).toBe(380);
  });
});
