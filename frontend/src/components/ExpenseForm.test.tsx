import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExpenseForm, emptyDraft } from "./ExpenseForm";
import type { Suggestion } from "../lib/types";

describe("ExpenseForm", () => {
  it("validates before submitting", async () => {
    const onSubmit = vi.fn();
    render(<ExpenseForm initial={emptyDraft()} submitLabel="Save expense" onSubmit={onSubmit} idPrefix="t" />);
    await userEvent.click(screen.getByRole("button", { name: "Save expense" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Add the merchant name.");
    await userEvent.type(screen.getByLabelText(/Merchant/), "DMart");
    await userEvent.type(screen.getByLabelText(/Total/), "0");
    await userEvent.click(screen.getByRole("button", { name: "Save expense" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Amount must be more than zero.");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("flags low-confidence OCR fields for review", () => {
    render(<ExpenseForm initial={{ ...emptyDraft(), merchant: "Hnen Of", amount: "22.49" }}
      confidence={{ merchant: 0.26, amount: 0.95 }} submitLabel="Save" onSubmit={vi.fn()} idPrefix="t" />);
    const merchant = screen.getByLabelText(/Merchant/).closest("label")!;
    expect(merchant).toHaveClass("flag");
    expect(merchant).toHaveTextContent("Check this");
    expect(screen.getByLabelText(/Total/).closest("label")).not.toHaveClass("flag");
    expect(screen.getByLabelText(/Total/).closest("label")).toHaveTextContent("read 95%");
  });

  it("saves an abstained suggestion as Uncategorised and reports the best guess", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const s: Suggestion = { category: "Shopping", confidence: 0.2, source: "model", status: "low_confidence",
      abstained: true, threshold: 0.35, alternatives: [{ category: "Shopping", p: 0.2 }], explanation: [] };
    render(<ExpenseForm initial={{ ...emptyDraft(), merchant: "Some Shop", amount: "120", category: "Uncategorised" }}
      suggestion={s} submitLabel="Save" onSubmit={onSubmit} idPrefix="t" />);
    expect(screen.getByLabelText("Category")).toHaveValue("Uncategorised");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      category: "Uncategorised", suggested_category: "Shopping", amount: 120,
    }));
  });

  it("shows the server error when saving fails", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("amount: Input should be greater than 0"));
    render(<ExpenseForm initial={{ ...emptyDraft(), merchant: "X", amount: "5", category: "Other" }}
      submitLabel="Save" onSubmit={onSubmit} idPrefix="t" />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("amount: Input should be greater than 0");
  });
});
