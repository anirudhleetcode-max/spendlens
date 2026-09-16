import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SuggestionNote } from "./SuggestionNote";
import { preselect } from "./ExpenseForm";
import type { Suggestion } from "../lib/types";

const base: Suggestion = {
  category: "Transport & Fuel", confidence: 0.91, source: "model", status: "confident", abstained: false,
  threshold: 0.35, model_version: "cat-test",
  alternatives: [{ category: "Transport & Fuel", p: 0.91 }, { category: "Shopping", p: 0.05 }],
  explanation: [{ token: "petrol", weight: 1.2, type: "word" }, { token: "speed petrol", weight: 0.8, type: "word" }],
};

describe("SuggestionNote", () => {
  it("shows a confident suggestion with the words that drove it", () => {
    render(<SuggestionNote suggestion={base} chosen="Transport & Fuel" onPick={() => {}} />);
    expect(screen.getByTestId("suggestion")).toHaveAttribute("data-status", "confident");
    expect(screen.getByText(/Suggested/)).toHaveTextContent("Suggested Transport & Fuel (91% sure)");
    expect(screen.getByTestId("suggestion-why")).toHaveTextContent("petrol");
    expect(screen.getByTestId("suggestion-why")).toHaveTextContent("speed petrol");
  });

  it("abstains below the threshold and offers the alternatives as choices", async () => {
    const onPick = vi.fn();
    const low: Suggestion = {
      ...base, status: "low_confidence", abstained: true, confidence: 0.28, category: "Shopping",
      alternatives: [{ category: "Shopping", p: 0.28 }, { category: "Other", p: 0.22 }, { category: "Health", p: 0.04 }],
    };
    render(<SuggestionNote suggestion={low} chosen="Uncategorised" onPick={onPick} />);
    const note = screen.getByTestId("suggestion");
    expect(note).toHaveAttribute("data-status", "low_confidence");
    expect(note).toHaveTextContent("Not sure");
    expect(note).toHaveTextContent("best guess Shopping at 28%, below the 35% bar");
    // below 8% is not offered
    expect(screen.queryByRole("button", { name: /Health/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Other 22%" }));
    expect(onPick).toHaveBeenCalledWith("Other");
  });

  it("explains when the model is unavailable", () => {
    render(<SuggestionNote suggestion={{ ...base, status: "unavailable", abstained: true, category: "Uncategorised",
      confidence: 0, alternatives: [], explanation: [], detail: "model file not found" }} chosen="Uncategorised" onPick={() => {}} />);
    expect(screen.getByTestId("suggestion")).toHaveTextContent("No automatic category right now (model file not found)");
  });

  it("marks a user correction", () => {
    render(<SuggestionNote suggestion={base} chosen="Travel" onPick={() => {}} />);
    expect(screen.getByTestId("suggestion")).toHaveTextContent("you changed it");
  });
});

describe("preselect", () => {
  it("never pre-selects a category the model abstained on", () => {
    expect(preselect(base)).toBe("Transport & Fuel");
    expect(preselect({ ...base, abstained: true, status: "low_confidence" })).toBe("Uncategorised");
    expect(preselect({ ...base, status: "unavailable" })).toBe("Uncategorised");
    expect(preselect(null)).toBe("");
  });
});
