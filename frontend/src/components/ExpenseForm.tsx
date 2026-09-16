import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { CATEGORIES, PAYMENT_MODES, UNCATEGORISED, type Category, type LineItem, type Suggestion } from "../lib/types";
import { pct, todayISO } from "../lib/format";
import { ItemsEditor } from "./ItemsEditor";
import { SuggestionNote } from "./SuggestionNote";

/** What the form should pre-select for a suggestion: nothing is guessed when the model abstains. */
// eslint-disable-next-line react-refresh/only-export-components
export function preselect(s: Suggestion | null | undefined): Category | "" {
  if (!s) return "";
  if (s.abstained || s.status === "low_confidence" || s.status === "unavailable") return UNCATEGORISED;
  return s.category;
}

export type Draft = {
  merchant: string;
  amount: string;
  date: string;
  category: Category | "";
  tax: string;
  payment_mode: string;
  notes: string;
  items: LineItem[];
};

export const emptyDraft = (): Draft => ({
  merchant: "", amount: "", date: todayISO(), category: "", tax: "0", payment_mode: "UPI", notes: "", items: [],
});

export type SubmitBody = {
  merchant: string; amount: number; date: string; category: Category; tax: number;
  payment_mode: string; notes: string; items: LineItem[]; suggested_category: Category | null;
};

type Props = {
  initial: Draft;
  confidence?: Partial<Record<"merchant" | "amount" | "date" | "tax" | "payment_mode", number>>;
  suggestion?: Suggestion | null;
  autoSuggest?: boolean;
  submitLabel: string;
  onSubmit: (body: SubmitBody) => Promise<void>;
  onCancel?: () => void;
  extra?: ReactNode;
  idPrefix?: string;
};

const LOW = 0.6;

function FlagNote({ c }: { c?: number }) {
  if (c === undefined) return null;
  if (c < LOW) return <span className="flag-note"><AlertTriangle aria-hidden />Check this</span>;
  return <span className="conf">read {pct(c)}</span>;
}

export function ExpenseForm({ initial, confidence, suggestion: initialSuggestion, autoSuggest, submitLabel, onSubmit, onCancel, extra, idPrefix = "f" }: Props) {
  const [d, setD] = useState<Draft>(initial);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(initialSuggestion ?? null);
  const [touchedCategory, setTouchedCategory] = useState(Boolean(initial.category) && !initialSuggestion);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((p) => ({ ...p, [k]: v }));

  // live suggestion while typing a merchant (manual entry)
  useEffect(() => {
    if (!autoSuggest) return;
    window.clearTimeout(timer.current);
    const merchant = d.merchant.trim();
    if (merchant.length < 3) return;
    timer.current = window.setTimeout(() => {
      api<Suggestion>("/api/categories/suggest", { method: "POST", json: { merchant, items: d.items.map((i) => i.name).filter(Boolean) } })
        .then((s) => {
          setSuggestion(s);
          if (!touchedCategory) setD((p) => ({ ...p, category: preselect(s) }));
        })
        .catch(() => undefined);
    }, 350);
    return () => window.clearTimeout(timer.current);
  }, [d.merchant, d.items, autoSuggest, touchedCategory]);

  const flag = (k: keyof NonNullable<Props["confidence"]>) =>
    confidence?.[k] !== undefined && (confidence[k] as number) < LOW ? " flag" : "";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const amount = Number(d.amount);
    if (!d.merchant.trim()) return setError("Add the merchant name.");
    if (!(amount > 0)) return setError("Amount must be more than zero.");
    if (!d.date) return setError("Pick the date on the bill.");
    const category = (d.category || preselect(suggestion) || UNCATEGORISED) as Category;
    setBusy(true);
    try {
      await onSubmit({
        merchant: d.merchant.trim(), amount, date: d.date, category, tax: Number(d.tax) || 0,
        payment_mode: d.payment_mode, notes: d.notes.trim(),
        items: d.items.filter((i) => i.name.trim()).map((i) => ({ name: i.name.trim(), qty: Number(i.qty) || 0, price: Number(i.price) || 0 })),
        // the model's best guess (even when it abstained) - a different choice is learned as a correction
        suggested_category: suggestion && suggestion.status !== "unavailable" && suggestion.category !== UNCATEGORISED
          ? suggestion.category : null,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  const id = (s: string) => `${idPrefix}-${s}`;

  return (
    <form onSubmit={submit} noValidate>
      <div className="form-grid">
        <label className={`field wide${flag("merchant")}`} htmlFor={id("merchant")}>
          <span>Merchant <FlagNote c={confidence?.merchant} /></span>
          <input id={id("merchant")} className="input" value={d.merchant} maxLength={80} autoComplete="off"
            placeholder="e.g. DMart, Swiggy, Indian Oil" onChange={(e) => set("merchant", e.target.value)} />
        </label>
        <label className={`field${flag("amount")}`} htmlFor={id("amount")}>
          <span>Total (₹) <FlagNote c={confidence?.amount} /></span>
          <input id={id("amount")} className="input num" type="number" inputMode="decimal" min={0} step="0.01"
            value={d.amount} onChange={(e) => set("amount", e.target.value)} placeholder="0.00" />
        </label>
        <label className={`field${flag("date")}`} htmlFor={id("date")}>
          <span>Date <FlagNote c={confidence?.date} /></span>
          <input id={id("date")} className="input" type="date" value={d.date} max={todayISO()}
            onChange={(e) => set("date", e.target.value)} />
        </label>
        <div className={`field wide${d.category === UNCATEGORISED ? " flag" : ""}`}>
          <label htmlFor={id("category")} style={{ fontSize: 13, fontWeight: 500, color: "var(--ink-2)" }}>Category</label>
          <select id={id("category")} className="select" value={d.category}
            onChange={(e) => { setTouchedCategory(true); set("category", e.target.value as Category); }}>
            {!d.category && <option value="">Choose…</option>}
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          {suggestion && (
            <SuggestionNote suggestion={suggestion} chosen={d.category}
              onPick={(c) => { setTouchedCategory(true); set("category", c); }} />
          )}
        </div>
        <label className={`field${flag("tax")}`} htmlFor={id("tax")}>
          <span>GST / tax (₹) <FlagNote c={confidence?.tax} /></span>
          <input id={id("tax")} className="input num" type="number" min={0} step="0.01" value={d.tax}
            onChange={(e) => set("tax", e.target.value)} />
        </label>
        <label className={`field${flag("payment_mode")}`} htmlFor={id("pm")}>
          <span>Paid via <FlagNote c={confidence?.payment_mode} /></span>
          <select id={id("pm")} className="select" value={d.payment_mode} onChange={(e) => set("payment_mode", e.target.value)}>
            {PAYMENT_MODES.map((m) => <option key={m} value={m}>{m === "Unknown" ? "Not sure" : m}</option>)}
          </select>
        </label>
        <div className="field wide">
          <span style={{ fontSize: 13, fontWeight: 500, color: "var(--ink-2)" }}>Line items</span>
          <ItemsEditor items={d.items} onChange={(items) => set("items", items)} />
        </div>
        <label className="field wide" htmlFor={id("notes")}>
          <span>Note</span>
          <input id={id("notes")} className="input" value={d.notes} maxLength={300} placeholder="Optional"
            onChange={(e) => set("notes", e.target.value)} />
        </label>
      </div>
      {error && <div className="notice error" role="alert" style={{ marginTop: 16 }}><AlertTriangle aria-hidden />{error}</div>}
      <div className="form-actions">
        {extra && <div className="spacer">{extra}</div>}
        {onCancel && <button type="button" className="btn" onClick={onCancel}>Cancel</button>}
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy && <Loader2 className="spin" aria-hidden />}{submitLabel}
        </button>
      </div>
    </form>
  );
}
