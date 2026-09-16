import { AlertTriangle, CheckCircle2, OctagonAlert } from "lucide-react";
import type { BudgetRow } from "../lib/types";

export function BudgetStatus({ status }: { status: BudgetRow["status"] }) {
  if (status === "over") return <span className="status over"><OctagonAlert aria-hidden />Over budget</span>;
  if (status === "at_risk") return <span className="status at_risk"><AlertTriangle aria-hidden />On pace to exceed</span>;
  return <span className="status ok"><CheckCircle2 aria-hidden />On track</span>;
}

export function BudgetBar({ row }: { row: BudgetRow }) {
  const max = Math.max(row.budget, row.spent, row.projected) || 1;
  return (
    <div className="bar-track" role="img"
      aria-label={`Spent ${Math.round(row.pct)}% of budget, projected ${Math.round((100 * row.projected) / row.budget)}%`}>
      <div className={`bar-fill ${row.status}`} style={{ width: `${Math.min(100, (100 * row.spent) / max)}%` }} />
      <div className="bar-marker" style={{ left: `calc(${Math.min(100, (100 * row.budget) / max)}% - 1px)` }} title="Budget" />
    </div>
  );
}
