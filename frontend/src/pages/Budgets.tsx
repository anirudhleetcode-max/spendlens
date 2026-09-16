import { useCallback, useEffect, useState, type FormEvent } from "react";
import { AlertTriangle, X } from "lucide-react";
import { api } from "../lib/api";
import { MODEL_CATEGORIES, type BudgetRow, type Category } from "../lib/types";
import { MonthPicker } from "../components/MonthPicker";
import { BudgetBar, BudgetStatus } from "../components/Status";
import { inr, inr0, monthName, thisMonth } from "../lib/format";
import { SkeletonRows } from "../components/Skeleton";
import { useToast } from "../components/Toast";

type Resp = { month: string; days_elapsed: number; days_in_month: number; budgets: BudgetRow[] };

export default function Budgets() {
  const [month, setMonth] = useState(thisMonth());
  const [data, setData] = useState<Resp | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api<Resp>(`/api/budgets?month=${month}`));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load budgets");
    }
  }, [month]);
  useEffect(() => { load(); }, [load]);

  const byCat = new Map(data?.budgets.map((b) => [b.category, b]));
  const totalBudget = data?.budgets.reduce((s, b) => s + b.budget, 0) ?? 0;
  const totalSpent = data?.budgets.reduce((s, b) => s + b.spent, 0) ?? 0;
  const current = month === thisMonth();

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Budgets</h1>
          <p className="muted">
            A monthly limit per category. {current && data
              ? `Projections assume you keep this month's pace — day ${data.days_elapsed} of ${data.days_in_month}.`
              : "Past months show the final spend."}
          </p>
        </div>
        <MonthPicker value={month} onChange={setMonth} />
      </div>

      {error && <div className="notice error" role="alert" style={{ marginBottom: 16 }}><AlertTriangle aria-hidden />{error}</div>}

      {!data ? (
        <SkeletonRows rows={10} label="Loading budgets" />
      ) : (
        <div className="table-scroll">
          <table className="ledger budget-table" data-testid="budget-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Monthly budget</th>
                <th className="amt"><span className="hide-sm">Spent in {monthName(month)}</span><span className="show-sm">Spent</span></th>
                <th className="hide-sm">Progress</th>
                {current && <th className="amt hide-sm">Projected</th>}
                <th className="hide-sm">Status</th>
              </tr>
            </thead>
            <tbody>
              {MODEL_CATEGORIES.map((c) => (
                <Row key={c} category={c} row={byCat.get(c)} current={current} onChange={load} onError={setError} />
              ))}
            </tbody>
            {data.budgets.length > 0 && (
              <tfoot>
                <tr>
                  <td>Budgeted categories</td>
                  <td className="num">{inr0(totalBudget)}</td>
                  <td className="amt num">{inr(totalSpent)}</td>
                  <td className="hide-sm" />
                  {current && <td className="hide-sm" />}
                  <td className="num small hide-sm">{Math.round((100 * totalSpent) / totalBudget)}% used</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </>
  );
}

function Row({ category, row, current, onChange, onError }: {
  category: Category; row?: BudgetRow; current: boolean; onChange: () => void; onError: (e: string) => void;
}) {
  const [value, setValue] = useState(row ? String(row.budget) : "");
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();
  useEffect(() => { setValue(row ? String(row.budget) : ""); }, [row]);
  const dirty = value !== (row ? String(row.budget) : "");

  async function save(e: FormEvent) {
    e.preventDefault();
    const amount = Number(value);
    if (!(amount > 0)) return onError(`Enter a budget above ₹0 for ${category}.`);
    setBusy(true);
    try {
      await api("/api/budgets", { method: "PUT", json: { category, amount } });
      notify(`${category} budget set to ${inr0(amount)} a month`);
      onChange();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    setBusy(true);
    try {
      await api(`/api/budgets/${encodeURIComponent(category)}`, { method: "DELETE" });
      notify(`Removed the ${category} budget`);
      onChange();
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr data-testid={`budget-${category}`}>
      <td style={{ fontWeight: 500 }}>
        {category}
        <div className="show-sm">{row ? <BudgetStatus status={row.status} /> : <span className="muted small">Not set</span>}</div>
      </td>
      <td>
        <form className="budget-form" onSubmit={save}>
          <label className="visually-hidden" htmlFor={`b-${category}`}>Budget for {category}</label>
          <input id={`b-${category}`} className="input num" type="number" min={0} step={100} placeholder="None"
            value={value} onChange={(e) => setValue(e.target.value)} />
          {dirty && <button className="btn btn-sm btn-primary" disabled={busy}>Set</button>}
          {row && !dirty && (
            <button type="button" className="btn btn-ghost btn-sm icon-btn hide-sm" aria-label={`Remove ${category} budget`}
              onClick={clear} disabled={busy}><X aria-hidden /></button>
          )}
        </form>
      </td>
      <td className="amt">{row ? inr(row.spent) : <span className="muted">—</span>}</td>
      <td className="barcell hide-sm">{row && <BudgetBar row={row} />}</td>
      {current && <td className="amt num hide-sm muted">{row ? inr0(row.projected) : ""}</td>}
      <td className="hide-sm">{row ? <BudgetStatus status={row.status} /> : <span className="muted small">Not set</span>}</td>
    </tr>
  );
}
