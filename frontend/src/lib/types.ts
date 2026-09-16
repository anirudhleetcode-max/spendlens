export const CATEGORIES = [
  "Groceries", "Food & Dining", "Transport & Fuel", "Shopping", "Health",
  "Bills & Utilities", "Entertainment", "Travel", "Education", "Other",
] as const;
export type Category = (typeof CATEGORIES)[number];
export const PAYMENT_MODES = ["UPI", "Card", "Cash", "Wallet", "Net Banking", "Unknown"] as const;

export type LineItem = { name: string; qty: number; price: number };

export type Anomaly = { z: number; ratio: number; median: number; reason: string };

export type Expense = {
  id: string;
  merchant: string;
  amount: number;
  tax: number;
  date: string;
  category: Category;
  payment_mode: string;
  items: LineItem[];
  notes: string;
  source: "scan" | "manual";
  receipt_id: string | null;
  suggested_category: string | null;
  anomaly: Anomaly | null;
};

export type ExpensePage = { items: Expense[]; total: number; sum: number; page: number; pages: number; limit: number };

export type Suggestion = {
  category: Category;
  confidence: number;
  source: "model" | "your correction";
  alternatives: { category: Category; p: number }[];
};

export type FieldVal<T> = { value: T; confidence: number };

export type ScanResult = {
  receipt_id: string;
  ocr_available: boolean;
  fields: {
    merchant: FieldVal<string>;
    date: FieldVal<string | null>;
    total: FieldVal<number | null>;
    tax: FieldVal<number>;
    payment_mode: FieldVal<string>;
  };
  items: (LineItem & { confidence: number })[];
  category: Suggestion;
  ocr: null | { mean_conf: number; skew: number; cropped: boolean; variant: string; ms: number;
    lines: { text: string; conf: number }[] };
  stored_bytes: number;
};

export type BudgetRow = {
  category: Category; budget: number; spent: number; projected: number; pct: number;
  status: "ok" | "at_risk" | "over"; remaining: number;
};

export type Overview = {
  month: string; total: number; count: number; tax: number;
  previous_month: string; previous_total: number; previous_to_date: number; compared_days: number | null; change_pct: number | null;
  by_category: { category: Category; total: number; count: number; previous: number }[];
  daily: { day: number; amount: number; cumulative: number }[];
  previous_daily: { day: number; amount: number; cumulative: number }[];
  top_merchants: { merchant: string; category: Category; total: number; count: number }[];
  anomalies: Expense[];
  budgets: BudgetRow[];
};

export type Health = { status: string; db: string; classifier: boolean;
  ocr: { available: boolean; version: string | null; cmd: string | null } };
