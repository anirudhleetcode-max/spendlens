import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { Checks } from "./Checks";
import { OcrOverlay } from "./OcrOverlay";

describe("Checks", () => {
  it("lists failures first and names the status for screen readers", () => {
    render(<Checks checks={[
      { id: "items_sum", status: "pass", field: "items", message: "Line items add up." },
      { id: "total_arithmetic", status: "fail", field: "total", message: "Total ₹150.00 ≠ subtotal ₹100.00 + tax ₹5.00 = ₹105.00." },
    ]} />);
    const items = within(screen.getByTestId("checks")).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("fail: Total ₹150.00 ≠");
    expect(items[1]).toHaveClass("pass");
  });

  it("renders nothing without checks", () => {
    const { container } = render(<Checks checks={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("OcrOverlay", () => {
  it("draws a box per word and counts low-confidence ones", () => {
    const { container } = render(<OcrOverlay preview={{ image: "data:image/jpeg;base64,", width: 100, height: 200, boxes: [
      { x: 0.1, y: 0.1, w: 0.2, h: 0.02, conf: 95, text: "DMART" },
      { x: 0.1, y: 0.2, w: 0.2, h: 0.02, conf: 31, text: "T0TAL" },
    ] }} />);
    expect(container.querySelectorAll("rect")).toHaveLength(2);
    expect(container.querySelectorAll("rect.low")).toHaveLength(1);
    expect(screen.getByText(/2 words read · 1 below 60%/)).toBeInTheDocument();
  });
});
