import { useEffect, useRef, useState, type DragEvent } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Camera, Check, CheckCircle2, FileImage, Loader2, PenLine, RotateCcw, ScanLine } from "lucide-react";
import { api } from "../lib/api";
import type { Expense, Health, ScanResult } from "../lib/types";
import { ExpenseForm, emptyDraft, preselect, type Draft, type SubmitBody } from "../components/ExpenseForm";
import { Checks } from "../components/Checks";
import { OcrOverlay } from "../components/OcrOverlay";
import { useToast } from "../components/Toast";
import { dateLabel, inr, todayISO } from "../lib/format";

const STEPS = ["Straightening and cleaning the photo", "Reading the text", "Finding merchant, date and total", "Suggesting a category"];
const MAX_MB = 8;

type Stage =
  | { kind: "idle" }
  | { kind: "reading"; preview: string }
  | { kind: "review"; preview: string; result: ScanResult }
  | { kind: "manual" }
  | { kind: "saved"; expense: Expense };

export default function Scan() {
  const [stage, setStage] = useState<Stage>({ kind: "idle" });
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [step, setStep] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const camRef = useRef<HTMLInputElement>(null);
  const { notify } = useToast();

  useEffect(() => { api<Health>("/api/health").then(setHealth).catch(() => undefined); }, []);
  useEffect(() => {
    if (stage.kind !== "reading") return;
    setStep(0);
    const t = window.setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 700);
    return () => window.clearInterval(t);
  }, [stage.kind]);

  const ocrOff = health && !health.ocr.available;

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return setError("That file isn't a JPG, PNG or WebP photo.");
    if (file.size > MAX_MB * 1024 * 1024) return setError(`That photo is over ${MAX_MB} MB. Try a smaller one.`);
    const preview = URL.createObjectURL(file);
    setStage({ kind: "reading", preview });
    const body = new FormData();
    body.append("file", file);
    try {
      const result = await api<ScanResult>("/api/receipts/scan", { method: "POST", body });
      setStage({ kind: "review", preview, result });
    } catch (e) {
      URL.revokeObjectURL(preview);
      setStage({ kind: "idle" });
      setError(e instanceof Error ? e.message : "Upload failed");
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDrag(false);
    handleFile(e.dataTransfer.files?.[0]);
  }

  function reset() {
    if (stage.kind === "review") {
      // unsaved scan: delete the stored photo now instead of waiting for the cleanup job
      api(`/api/receipts/${stage.result.receipt_id}`, { method: "DELETE" }).catch(() => undefined);
    }
    if (stage.kind === "review" || stage.kind === "reading") URL.revokeObjectURL(stage.preview);
    setStage({ kind: "idle" });
    setError(null);
    if (fileRef.current) fileRef.current.value = "";
    if (camRef.current) camRef.current.value = "";
  }

  async function save(body: SubmitBody, receiptId?: string) {
    const expense = await api<Expense>("/api/expenses", { method: "POST", json: { ...body, receipt_id: receiptId ?? null } });
    if (stage.kind === "review") URL.revokeObjectURL(stage.preview);
    setStage({ kind: "saved", expense });
    notify(`Saved ${expense.merchant} to your ledger`);
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Scan a receipt</h1>
          <p className="muted">Printed bills work best — supermarket, restaurant, pharmacy, fuel.</p>
        </div>
        {stage.kind !== "idle" && stage.kind !== "reading" && (
          <button className="btn" onClick={reset}>
            <RotateCcw aria-hidden />{stage.kind === "review" ? "Discard scan" : "Start over"}
          </button>
        )}
      </div>

      {ocrOff && stage.kind !== "saved" && (
        <div className="notice" role="status" style={{ marginBottom: 20 }}>
          <AlertTriangle aria-hidden />
          <div>
            <b>Text reading is off on this server.</b> Tesseract OCR isn't installed or can't be found, so the fields won't fill in
            by themselves. You can still attach the photo and type the details — install Tesseract and set <code>TESSERACT_CMD</code> in
            <code>backend/.env</code> to turn it on (see README).
          </div>
        </div>
      )}
      {error && <div className="notice error" role="alert" style={{ marginBottom: 20 }}><AlertTriangle aria-hidden />{error}</div>}

      {stage.kind === "idle" && (
        <>
          <div className={`dropzone${drag ? " drag" : ""}`} onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)} onDrop={onDrop} data-testid="dropzone">
            <ScanLine className="big-icon" aria-hidden />
            <h2>Drop a photo of the bill here</h2>
            <p className="muted">JPG, PNG or WebP, up to {MAX_MB} MB.</p>
            <div className="row">
              <button className="btn btn-primary" onClick={() => fileRef.current?.click()}><FileImage aria-hidden />Choose photo</button>
              <button className="btn" onClick={() => camRef.current?.click()}><Camera aria-hidden />Use camera</button>
              <button className="btn btn-ghost" onClick={() => setStage({ kind: "manual" })}><PenLine aria-hidden />Type it in instead</button>
            </div>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden data-testid="file-input"
              onChange={(e) => handleFile(e.target.files?.[0])} />
            <input ref={camRef} type="file" accept="image/*" capture="environment" hidden
              onChange={(e) => handleFile(e.target.files?.[0])} />
          </div>
          <div className="scan-tips">
            <p><strong>Lay it flat</strong>A dark table behind the paper helps us find its edges and straighten it.</p>
            <p><strong>Fill the frame</strong>Get the whole bill in, top to the total. Tilted is fine, blurry isn't.</p>
            <p><strong>Check the orange fields</strong>We mark anything we read with low confidence. Fix it before saving.</p>
          </div>
        </>
      )}

      {stage.kind === "reading" && (
        <div className="review">
          <div className="receipt-pane">
            <div className="receipt-frame"><img src={stage.preview} alt="Receipt being read" /></div>
          </div>
          <div aria-live="polite">
            <h2 style={{ display: "flex", alignItems: "center", gap: 8 }}><Loader2 className="spin" size={18} aria-hidden />Reading your receipt…</h2>
            <ul className="progress-steps">
              {STEPS.map((s, i) => (
                <li key={s} className={i < step ? "done" : ""}>
                  {i < step ? <Check aria-hidden /> : i === step ? <Loader2 className="spin" aria-hidden /> : <span style={{ width: 14 }} />}{s}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {stage.kind === "review" && <Review stage={stage} onSave={save} onCancel={reset} />}

      {stage.kind === "manual" && (
        <div className="panel" style={{ maxWidth: 720 }}>
          <div className="panel-head"><h2>New expense</h2></div>
          <ExpenseForm initial={emptyDraft()} autoSuggest submitLabel="Save expense" onSubmit={(b) => save(b)} onCancel={reset} idPrefix="manual" />
        </div>
      )}

      {stage.kind === "saved" && (
        <div className="saved" role="status">
          <p className="eyebrow" style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--green-ink)" }}>
            <CheckCircle2 size={14} aria-hidden />Saved to your ledger
          </p>
          <p className="value num">{inr(stage.expense.amount)}</p>
          <p>{stage.expense.merchant} · {stage.expense.category} · {dateLabel(stage.expense.date)}</p>
          <div className="row" style={{ display: "flex", gap: 8, marginTop: 20, flexWrap: "wrap" }}>
            <button className="btn btn-primary" onClick={reset}><ScanLine aria-hidden />Scan another</button>
            <Link className="btn" to="/expenses">View expenses</Link>
            <Link className="btn btn-ghost" to="/">Back to overview</Link>
          </div>
        </div>
      )}
    </>
  );
}

function Review({ stage, onSave, onCancel }: {
  stage: { preview: string; result: ScanResult };
  onSave: (b: SubmitBody, receiptId: string) => Promise<void>;
  onCancel: () => void;
}) {
  const { result: r, preview: photo } = stage;
  const f = r.fields;
  const initial: Draft = {
    merchant: f.merchant.value ?? "",
    amount: f.total.value != null ? f.total.value.toFixed(2) : "",
    date: f.date.value ?? todayISO(),
    category: preselect(r.category),
    tax: (f.tax.value ?? 0).toFixed(2),
    payment_mode: f.payment_mode.value ?? "Unknown",
    notes: "",
    items: r.items.map((i) => ({ name: i.name, qty: i.qty, price: i.price })),
  };
  const confidence = r.ocr_available ? {
    merchant: f.merchant.confidence, amount: f.total.confidence, date: f.date.confidence,
    tax: f.tax.confidence, payment_mode: f.payment_mode.confidence,
  } : undefined;
  const threshold = r.review_threshold ?? 0.6;
  const flagged = confidence ? Object.values(confidence).filter((c) => c < threshold).length : 0;
  const [view, setView] = useState<"photo" | "ocr">("photo");
  const preview = r.ocr?.preview;

  return (
    <div className="review" data-testid="review">
      <div className="receipt-pane">
        {preview && (
          <div className="segmented" role="tablist" aria-label="Receipt view">
            <button role="tab" aria-selected={view === "photo"} className={view === "photo" ? "on" : ""}
              onClick={() => setView("photo")}>Your photo</button>
            <button role="tab" aria-selected={view === "ocr"} className={view === "ocr" ? "on" : ""}
              onClick={() => setView("ocr")}>What OCR read</button>
          </div>
        )}
        {view === "ocr" && preview
          ? <OcrOverlay preview={preview} />
          : <div className="receipt-frame"><img src={photo} alt="Uploaded receipt" /></div>}
        {r.ocr && (
          <>
            <div className="ocr-meta num">
              <span>OCR confidence {Math.round(r.ocr.mean_conf)}%</span>
              {r.ocr.cropped && <span>edges found and flattened</span>}
              {Math.abs(r.ocr.skew) > 0.3 && <span>straightened {Math.abs(r.ocr.skew).toFixed(1)}°</span>}
              <span>{(r.ocr.ms / 1000).toFixed(1)} s</span>
            </div>
            <details className="ocr-text">
              <summary>Show the text we read</summary>
              <pre>{r.ocr.lines.map((l, i) => (
                <span key={i} className={l.conf < 60 ? "low-line" : ""}>{l.text}{"\n"}</span>
              ))}</pre>
            </details>
          </>
        )}
      </div>
      <div>
        <h2>Check the details</h2>
        <p className="muted small" style={{ margin: "4px 0 12px" }}>
          {!r.ocr_available ? "Fill these in from the photo."
            : flagged ? `${flagged} field${flagged > 1 ? "s" : ""} marked in orange — we weren't sure about ${flagged > 1 ? "them" : "it"}.`
            : "Everything read cleanly. Give it a glance and save."}
          {" "}Nothing is saved until you press Save; an unsaved photo is deleted within {r.expires_hours ?? 24} h.
        </p>
        <Checks checks={r.checks ?? []} />
        <ExpenseForm initial={initial} confidence={confidence} suggestion={r.category}
          autoSuggest={!r.ocr_available} submitLabel="Save expense" idPrefix="scan"
          onSubmit={(b) => onSave(b, r.receipt_id)} onCancel={onCancel} />
      </div>
    </div>
  );
}
