import { AlertTriangle, Info, Sparkles } from "lucide-react";
import type { Category, Suggestion } from "../lib/types";
import { pct } from "../lib/format";

type Props = {
  suggestion: Suggestion;
  chosen: Category | "";
  onPick: (c: Category) => void;
};

/** Explains the category suggestion: how sure, why, and what to do when the model abstains. */
export function SuggestionNote({ suggestion: s, chosen, onPick }: Props) {
  const status = s.status ?? (s.source === "your correction" ? "override" : "confident");
  const corrected = status !== "unavailable" && chosen && chosen !== "Uncategorised" && chosen !== s.category;
  const why = (s.explanation ?? []).map((e) => e.token).filter(Boolean).slice(0, 4);
  const alts = s.alternatives.filter((a) => a.p >= 0.08 && a.category !== chosen);

  if (status === "override") {
    return (
      <div className="suggest-line" data-testid="suggestion" data-status="override">
        <Sparkles size={12} aria-hidden />
        Using your earlier choice for this merchant: <b>{s.category}</b>
      </div>
    );
  }
  if (status === "unavailable") {
    return (
      <div className="suggest-line warn" data-testid="suggestion" data-status="unavailable">
        <Info size={12} aria-hidden />
        No automatic category right now{s.detail ? ` (${s.detail})` : ""}. Pick one.
      </div>
    );
  }
  return (
    <div className={`suggest-line${status === "low_confidence" ? " warn" : ""}`} data-testid="suggestion" data-status={status}>
      {status === "low_confidence" ? (
        <>
          <AlertTriangle size={12} aria-hidden />
          <span>
            <b>Not sure</b> — best guess {s.category} at {pct(s.confidence)}, below the {pct(s.threshold ?? 0.5)} bar.
            Pick a category or leave it Uncategorised.
          </span>
        </>
      ) : (
        <>
          <Sparkles size={12} aria-hidden />
          <span>Suggested <b>{s.category}</b> ({pct(s.confidence)} sure)</span>
        </>
      )}
      {why.length > 0 && (
        <span className="why" data-testid="suggestion-why">because of: {why.map((w) => <q key={w}>{w}</q>)}</span>
      )}
      {corrected && <span>· you changed it — we'll remember this merchant</span>}
      {!corrected && alts.map((a) => (
        <button type="button" key={a.category} className="chip" onClick={() => onPick(a.category)}>
          {a.category} {pct(a.p)}
        </button>
      ))}
    </div>
  );
}
