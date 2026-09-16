import { ChevronLeft, ChevronRight } from "lucide-react";
import { monthLabel, shiftMonth, thisMonth } from "../lib/format";

export function MonthPicker({ value, onChange }: { value: string; onChange: (m: string) => void }) {
  const atCurrent = value >= thisMonth();
  return (
    <div className="pager" role="group" aria-label="Month">
      <button className="btn btn-sm icon-btn" onClick={() => onChange(shiftMonth(value, -1))} aria-label="Previous month">
        <ChevronLeft aria-hidden />
      </button>
      <span className="num" style={{ minWidth: 128, textAlign: "center", fontWeight: 500 }} aria-live="polite">
        {monthLabel(value)}
      </span>
      <button className="btn btn-sm icon-btn" onClick={() => onChange(shiftMonth(value, 1))} disabled={atCurrent} aria-label="Next month">
        <ChevronRight aria-hidden />
      </button>
    </div>
  );
}
