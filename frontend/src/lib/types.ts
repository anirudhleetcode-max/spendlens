export const MODEL_CATEGORIES = [
  "Groceries", "Food & Dining", "Transport & Fuel", "Shopping", "Health",
  "Bills & Utilities", "Entertainment", "Travel", "Education", "Other",
] as const;
export const UNCATEGORISED = "Uncategorised" as const;
export const CATEGORIES = [...MODEL_CATEGORIES, UNCATEGORISED] as const;
export type Category = (typeof CATEGORIES)[number];
export const PAYMENT_MODES = ["UPI", "Card", "Cash", "Wallet", "Net Banking", "Unknown"] as const;

export type LineItem = { name: string; qty: number; price: number };

export type Anomaly = { z: number; ratio: number; median: number; reason: string; detail?: string };

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
  demo?: boolean;
  created_at?: string | null;
};

export type ExpensePage = { items: Expense[]; total: number; sum: number; page: number; pages: number; limit: number };

export type SuggestionStatus = "confident" | "low_confidence" | "override" | "unavailable";

export type Suggestion = {
  category: Category;
  confidence: number;
  source: "model" | "your correction" | "unavailable";
  alternatives: { category: Category; p: number }[];
  status?: SuggestionStatus;
  abstained?: boolean;
  threshold?: number;
  explanation?: { token: string; weight: number; type: string }[];
  model_version?: string | null;
  detail?: string;
};

export type FieldVal<T> = { value: T; confidence: number; source?: string; line?: number };

export type Check = { id: string; status: "pass" | "warn" | "fail" | "info"; field: string; message: string };

export type OcrPreview = {
  image: string; width: number; height: number;
  boxes: { x: number; y: number; w: number; h: number; conf: number; text: string }[];
};

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
  checks?: Check[];
  review_threshold?: number;
  parser_version?: string | null;
  ocr: null | { mean_conf: number; skew: number; cropped: boolean; variant: string; ms: number;
    lines: { text: string; conf: number }[]; preview?: OcrPreview | null };
  stored_bytes: number;
  expires_hours?: number;
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

export type Health = { status: string; db: string; classifier: boolean; degraded?: string[];
  ocr: { available: boolean; version: string | null; cmd: string | null };
  model?: { status: string; version: string | null; error: string | null } };

export type ReceiptEval = { run_id: string | null; dataset: string; synthetic: boolean; n: number;
  merchant_exact: number | null; date_exact: number | null; total_exact: number | null; cer: number | null } | null;

export type ModelCard = {
  model: string; version: string; trained_at: string; algorithm: string; kind: string;
  hyperparameters: Record<string, unknown>; features_version: string; seed: number; classes: string[];
  training_data: { name: string; synthetic: boolean; size: number; user_corrections: number; sha256: string; description: string };
  calibration: { method: string; temperature: number; fitted_on: string };
  abstention: { threshold: number; rule: string; chosen_for: string };
  evaluation: {
    run_id?: string; dataset?: string; test_size?: number; test_accuracy?: number; test_macro_f1?: number;
    test_merchant_only_accuracy?: number; test_ece_before_calibration?: number; test_ece_after_calibration?: number;
    test_coverage_at_threshold?: number; test_accuracy_at_threshold?: number | null;
    baselines_test_macro_f1?: Record<string, number>; note?: string;
  };
  libraries: Record<string, string>; intended_use: string; limitations: string[];
};

export type ModelInfo = {
  category_model: { status: string; error: string | null; version: string | null; kind: string | null;
    threshold: number | null; temperature: number | null; feedback_rows: number | null; card: ModelCard | null };
  receipt_pipeline: { ocr: Health["ocr"]; preprocess_version: string; parser_version: string;
    review_threshold: number; method: string };
  anomaly_rule: { z_threshold: number; min_ratio: number; min_history: number; window_days: number };
  evaluations: { receipts_real_sroie: ReceiptEval; receipts_real_cord: ReceiptEval; receipts_synthetic_test: ReceiptEval };
  notes: string[];
};
