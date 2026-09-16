import { AlertTriangle, CheckCircle2, Info, OctagonAlert } from "lucide-react";
import type { Check } from "../lib/types";

const ICON = { pass: CheckCircle2, warn: AlertTriangle, fail: OctagonAlert, info: Info };

/** Validation results from the receipt parser: why a field is (or isn't) trusted. */
export function Checks({ checks }: { checks: Check[] }) {
  if (!checks.length) return null;
  const order = { fail: 0, warn: 1, info: 2, pass: 3 };
  const sorted = [...checks].sort((a, b) => order[a.status] - order[b.status]);
  return (
    <ul className="checks" aria-label="Receipt checks" data-testid="checks">
      {sorted.map((c) => {
        const Icon = ICON[c.status];
        return (
          <li key={c.id} className={`check ${c.status}`}>
            <Icon aria-hidden />
            <span><span className="visually-hidden">{c.status}: </span>{c.message}</span>
          </li>
        );
      })}
    </ul>
  );
}
