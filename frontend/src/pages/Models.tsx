import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { api } from "../lib/api";
import type { ModelInfo, ReceiptEval } from "../lib/types";
import { SkeletonBlock } from "../components/Skeleton";

const p = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? "Not measured yet" : `${(v * 100).toFixed(digits)}%`;

const BASELINE_NAMES: Record<string, string> = {
  majority: "Majority class", keyword_rules: "Keyword rules", complement_nb: "TF-IDF + ComplementNB", logreg: "TF-IDF + LogisticRegression",
};

function DataBadge({ synthetic }: { synthetic: boolean | undefined }) {
  return synthetic
    ? <span className="pill warn">synthetic data</span>
    : <span className="pill ok">real data</span>;
}

function EvalRow({ label, e, note }: { label: string; e: ReceiptEval; note: string }) {
  if (!e) {
    return (
      <tr><td>{label}</td><td colSpan={5} className="muted">Dataset required before evaluation.</td><td>{note}</td></tr>
    );
  }
  return (
    <tr>
      <td>{label} <DataBadge synthetic={e.synthetic} /></td>
      <td className="amt num">{e.n}</td>
      <td className="amt num">{e.merchant_exact === null ? "—" : p(e.merchant_exact, 1)}</td>
      <td className="amt num">{e.date_exact === null ? "—" : p(e.date_exact, 1)}</td>
      <td className="amt num">{p(e.total_exact, 1)}</td>
      <td className="amt num">{e.cer === null ? "—" : e.cer.toFixed(2)}</td>
      <td className="small muted">{note} Parser {e.parser_version ?? "?"}.<br /><code>{e.run_id}</code></td>
    </tr>
  );
}

export default function Models() {
  const [info, setInfo] = useState<ModelInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<ModelInfo>("/api/model").then(setInfo).catch((e) => setError(e instanceof Error ? e.message : "Could not load"));
  }, []);

  const cm = info?.category_model;
  const card = cm?.card;
  const ev = card?.evaluation;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>How the models work</h1>
          <p className="muted">What runs on your receipts, what it was tested on, and where it falls short.</p>
        </div>
      </div>
      {error && <div className="notice error" role="alert"><AlertTriangle aria-hidden />{error}</div>}
      {!info && !error && <SkeletonBlock height={320} />}
      {info && (
        <div className="grid-2 models">
          <div>
            <section className="section" aria-labelledby="pipe-h">
              <div className="section-head"><h2 id="pipe-h">Receipt reading</h2>
                <span className="small muted">parser v{info.receipt_pipeline.parser_version} · preprocessing v{info.receipt_pipeline.preprocess_version}</span>
              </div>
              <ol className="pipeline-steps">
                <li><b>Clean up the photo</b> — find the paper and flatten it, remove noise, straighten the text, sharpen contrast (OpenCV).</li>
                <li><b>Read the text</b> — Tesseract {info.receipt_pipeline.ocr.version ?? ""} reads two versions of the image and keeps the one it is surer about.
                  {info.receipt_pipeline.ocr.available
                    ? <span className="status ok"> <CheckCircle2 aria-hidden />available</span>
                    : <span className="status over"> <AlertTriangle aria-hidden />not installed on this server</span>}</li>
                <li><b>Find the fields</b> — rules look for the merchant, a dated line, the grand-total line, GST lines and item rows.</li>
                <li><b>Check the arithmetic</b> — subtotal + GST + round-off should equal the total; if not, the total is flagged (or repaired when one misread digit explains it).</li>
                <li><b>Score each field</b> — OCR confidence × how strong the rule was × whether the checks passed. Below {Math.round(info.receipt_pipeline.review_threshold * 100)}% a field is marked for you to check. These scores rank evidence; they are not probabilities.</li>
              </ol>
              <h3 style={{ margin: "20px 0 8px" }}>Measured accuracy (exact match)</h3>
              <div className="table-scroll">
                <table className="ledger" data-testid="receipt-evals">
                  <thead><tr><th>Test set</th><th className="amt">Receipts</th><th className="amt">Merchant</th><th className="amt">Date</th><th className="amt">Total</th><th className="amt">CER</th><th>Notes</th></tr></thead>
                  <tbody>
                    <EvalRow label="SROIE test" e={info.evaluations.receipts_real_sroie} note="Real Malaysian receipts, scored blind before the total-line fix; merchants aren't in our Indian list." />
                    {info.evaluations.receipts_real_sroie_dev !== undefined && (
                      <EvalRow label="SROIE dev" e={info.evaluations.receipts_real_sroie_dev ?? null} note="Different SROIE receipts used to check the fix." />
                    )}
                    <EvalRow label="CORD" e={info.evaluations.receipts_real_cord} note="Real Indonesian receipts; totals use '.' for thousands." />
                    <EvalRow label="Generated Indian bills" e={info.evaluations.receipts_synthetic_test} note="Our own generator — easier than real photos." />
                  </tbody>
                </table>
              </div>
              <p className="small muted" style={{ marginTop: 8 }}>CER = character error rate of the OCR text (lower is better). No labelled set of Indian receipts was available.</p>
            </section>
            <section className="section" aria-labelledby="anom-h2">
              <div className="section-head"><h2 id="anom-h2">"Worth a look" flags</h2></div>
              <p>An expense is flagged when it is far above <i>your own</i> typical amount for that category: robust z-score above {info.anomaly_rule.z_threshold} (median and MAD of your last {info.anomaly_rule.window_days} days) <b>and</b> at least {info.anomaly_rule.min_ratio}× the median. It needs {info.anomaly_rule.min_history} past expenses in the category. It is a rule, not a trained model, and it only looks at amounts.</p>
            </section>
          </div>
          <div>
            <section className="section" aria-labelledby="cat-h2" data-testid="model-card">
              <div className="section-head"><h2 id="cat-h2">Category suggestions</h2>
                {card && <DataBadge synthetic={card.training_data.synthetic} />}
              </div>
              {cm?.status !== "ready" && (
                <div className="notice" role="status"><AlertTriangle aria-hidden />
                  <span>The category model is <b>{cm?.status}</b>{cm?.error ? `: ${cm.error}` : ""}. Expenses are saved as Uncategorised until it is back.</span>
                </div>
              )}
              {card ? (
                <>
                  <dl className="facts">
                    <dt>Model</dt><dd>{card.algorithm}</dd>
                    <dt>Version</dt><dd><code>{card.version}</code>, trained {new Date(card.trained_at).toLocaleDateString("en-IN")}</dd>
                    <dt>Training data</dt><dd>{card.training_data.size.toLocaleString("en-IN")} <b>synthetic</b> examples{card.training_data.user_corrections ? ` + ${card.training_data.user_corrections} user corrections` : ""}. {card.training_data.description}</dd>
                    <dt>Confidence</dt><dd>Temperature-scaled (T = {card.calibration.temperature}) on a validation split.</dd>
                    <dt>Abstains below</dt><dd>{p(card.abstention.threshold)} — then the expense is left Uncategorised for you to pick.</dd>
                    <dt>Personal memory</dt><dd>When you change a category, that merchant uses your choice from then on.</dd>
                  </dl>
                  <h3 style={{ margin: "20px 0 8px" }}>Test results on held-out synthetic shops and items</h3>
                  {ev?.note && <p className="small muted">{ev.note}</p>}
                  <table className="ledger">
                    <thead><tr><th>Model</th><th className="amt">Macro-F1</th></tr></thead>
                    <tbody>
                      {Object.entries(ev?.baselines_test_macro_f1 ?? {}).map(([k, v]) => (
                        <tr key={k} className={k === card.kind ? "selected-row" : ""}>
                          <td>{BASELINE_NAMES[k] ?? k}{k === card.kind && <span className="pill ok">in use</span>}</td>
                          <td className="amt num">{v.toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <dl className="facts" style={{ marginTop: 12 }}>
                    <dt>Accuracy</dt><dd>{p(ev?.test_accuracy, 1)} on {ev?.test_size ?? "?"} examples</dd>
                    <dt>Merchant name only</dt><dd>{p(ev?.test_merchant_only_accuracy, 1)} — an unknown shop name alone is often ambiguous</dd>
                    <dt>Calibration error</dt><dd>ECE {ev?.test_ece_before_calibration ?? "—"} → {ev?.test_ece_after_calibration ?? "—"} after scaling</dd>
                    <dt>When it does suggest</dt><dd>{p(ev?.test_accuracy_at_threshold, 1)} correct, covering {p(ev?.test_coverage_at_threshold)} of examples</dd>
                  </dl>
                  <h3 style={{ margin: "20px 0 8px" }}>Limitations</h3>
                  <ul className="plain-list">{card.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
                </>
              ) : cm?.status === "ready" ? <p className="muted">No model card found for this model file.</p> : null}
            </section>
          </div>
        </div>
      )}
    </>
  );
}
