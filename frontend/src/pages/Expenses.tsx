import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Download, Loader2, Plus, ReceiptText, Search, Trash2, X } from "lucide-react";
import { api, downloadFile } from "../lib/api";
import { CATEGORIES, type Expense, type ExpensePage } from "../lib/types";
import { ExpenseForm, emptyDraft, type SubmitBody } from "../components/ExpenseForm";
import { ReceiptImage } from "../components/ReceiptImage";
import { dateLabel, dayMonth, inr, monthLabel, shiftMonth, thisMonth } from "../lib/format";

const LIMIT = 15;
const MONTHS = Array.from({ length: 12 }, (_, i) => shiftMonth(thisMonth(), -i));

export default function Expenses() {
  const [month, setMonth] = useState(thisMonth());
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ExpensePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Expense | "new" | null>(null);
  const [viewing, setViewing] = useState<Expense | null>(null);
  const [exporting, setExporting] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const t = window.setTimeout(() => { setQuery(q.trim()); setPage(1); }, 300);
    return () => window.clearTimeout(t);
  }, [q]);

  const load = useCallback(async () => {
    setLoading(true);
    const p = new URLSearchParams({ page: String(page), limit: String(LIMIT) });
    if (month) p.set("month", month);
    if (category) p.set("category", category);
    if (query) p.set("q", query);
    try {
      setData(await api<ExpensePage>(`/api/expenses?${p}`));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load expenses");
    } finally {
      setLoading(false);
    }
  }, [month, category, query, page]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const d = dialogRef.current;
    if (!d) return;
    if (viewing && !d.open) d.showModal();
    if (!viewing && d.open) d.close();
  }, [viewing]);

  async function save(body: SubmitBody) {
    if (editing === "new") {
      await api("/api/expenses", { method: "POST", json: body });
    } else if (editing) {
      const { suggested_category: _s, ...patch } = body;
      void _s;
      await api(`/api/expenses/${editing.id}`, { method: "PATCH", json: patch });
    }
    setEditing(null);
    await load();
  }

  async function remove(e: Expense) {
    if (!window.confirm(`Delete ${e.merchant} (${inr(e.amount)}) from ${dateLabel(e.date)}?`)) return;
    try {
      await api(`/api/expenses/${e.id}`, { method: "DELETE" });
      if (editing !== "new" && editing?.id === e.id) setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete");
    }
  }

  async function exportCsv() {
    setExporting(true);
    try {
      await downloadFile(`/api/expenses/export?month=${month || thisMonth()}`, `spendlens-${month}.csv`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const from = data && data.total ? (data.page - 1) * data.limit + 1 : 0;
  const to = data ? Math.min(data.page * data.limit, data.total) : 0;
  const filtered = Boolean(category || query);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Expenses</h1>
          <p className="muted">{month ? monthLabel(month) : "All time"}{data ? ` · ${data.total} entr${data.total === 1 ? "y" : "ies"} · ${inr(data.sum)}` : ""}</p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn" onClick={exportCsv} disabled={exporting || !month} title={month ? "" : "Pick a month to export"}>
            {exporting ? <Loader2 className="spin" aria-hidden /> : <Download aria-hidden />}Export CSV
          </button>
          <button className="btn btn-primary" onClick={() => setEditing("new")}><Plus aria-hidden />Add expense</button>
        </div>
      </div>

      {editing && (
        <div className="panel">
          <div className="panel-head">
            <h2>{editing === "new" ? "New expense" : `Edit · ${editing.merchant}`}</h2>
            <button className="btn btn-ghost btn-sm icon-btn" aria-label="Close" onClick={() => setEditing(null)}><X aria-hidden /></button>
          </div>
          <ExpenseForm
            key={editing === "new" ? "new" : editing.id}
            idPrefix="exp"
            initial={editing === "new" ? emptyDraft() : {
              merchant: editing.merchant, amount: String(editing.amount), date: editing.date, category: editing.category,
              tax: String(editing.tax), payment_mode: editing.payment_mode, notes: editing.notes, items: editing.items,
            }}
            autoSuggest={editing === "new"}
            submitLabel={editing === "new" ? "Save expense" : "Save changes"}
            onSubmit={save}
            onCancel={() => setEditing(null)}
            extra={editing !== "new" && (
              <button type="button" className="btn btn-ghost btn-danger" onClick={() => remove(editing)}><Trash2 aria-hidden />Delete</button>
            )}
          />
        </div>
      )}

      <div className="toolbar" role="search">
        <label className="search">
          <span className="visually-hidden">Search</span>
          <Search aria-hidden />
          <input className="input" placeholder="Search merchant, item or note" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <label>
          <span className="visually-hidden">Month</span>
          <select className="select" value={month} onChange={(e) => { setMonth(e.target.value); setPage(1); }} aria-label="Month">
            {MONTHS.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
            <option value="">All time</option>
          </select>
        </label>
        <label>
          <span className="visually-hidden">Category</span>
          <select className="select" value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }} aria-label="Category">
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        {filtered && <button className="btn btn-ghost btn-sm" onClick={() => { setQ(""); setCategory(""); }}>Clear filters</button>}
      </div>

      {error && <div className="notice error" role="alert" style={{ marginBottom: 16 }}><AlertTriangle aria-hidden />{error}</div>}

      {data && data.items.length === 0 && !loading ? (
        <div className="empty">
          <h3>{filtered ? "Nothing matches those filters" : `No expenses in ${month ? monthLabel(month) : "your ledger"} yet`}</h3>
          <p>{filtered ? "Try another category or search term." : "Scan a bill or add one by hand — it'll show up here."}</p>
        </div>
      ) : (
        <div className="table-scroll" aria-busy={loading}>
          <table className="ledger" data-testid="expense-table" style={{ opacity: loading && data ? 0.6 : 1 }}>
            <thead>
              <tr>
                <th className="col-date">Date</th>
                <th>Merchant</th>
                <th className="hide-sm">Category</th>
                <th className="hide-sm">Paid via</th>
                <th className="amt">Amount</th>
                <th className="actions"><span className="visually-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {!data && loading && <tr><td colSpan={6} className="muted"><Loader2 className="spin" size={14} aria-hidden /> Loading…</td></tr>}
              {data?.items.map((e) => (
                <tr key={e.id} className="clickable" onClick={() => setEditing(e)} data-testid="expense-row">
                  <td className="num muted col-date">{dayMonth(e.date)}</td>
                  <td>
                    <div className="merchant-cell">
                      <span className="merchant-name">{e.merchant}</span>
                      <span className="small muted show-sm">{e.category}</span>
                      {e.anomaly && (
                        <span className="anomaly-note" title={`Typical: ${inr(e.anomaly.median)}`}>
                          <AlertTriangle aria-hidden />{e.anomaly.reason}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="hide-sm"><span className="tag">{e.category}</span></td>
                  <td className="hide-sm muted small">{e.payment_mode === "Unknown" ? "—" : e.payment_mode}</td>
                  <td className="amt">{inr(e.amount)}</td>
                  <td className="actions" onClick={(ev) => ev.stopPropagation()}>
                    {e.receipt_id && (
                      <button className="btn btn-ghost btn-sm icon-btn" aria-label={`View receipt for ${e.merchant}`} title="View receipt"
                        onClick={() => setViewing(e)}><ReceiptText aria-hidden /></button>
                    )}
                    <button className="btn btn-ghost btn-sm icon-btn btn-danger hide-sm" aria-label={`Delete ${e.merchant}`} title="Delete"
                      onClick={() => remove(e)}><Trash2 aria-hidden /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total > 0 && (
        <div className="table-foot">
          <span className="num">Showing {from}–{to} of {data.total}</span>
          <div className="pager">
            <button className="btn btn-sm icon-btn" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft aria-hidden /></button>
            <span className="num" style={{ padding: "0 8px" }}>Page {data.page} of {data.pages}</span>
            <button className="btn btn-sm icon-btn" disabled={page >= data.pages} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight aria-hidden /></button>
          </div>
        </div>
      )}

      <dialog ref={dialogRef} className="viewer" onClose={() => setViewing(null)} aria-label="Receipt">
        {viewing?.receipt_id && (
          <>
            <div className="viewer-head">
              <span><b>{viewing.merchant}</b> <span className="muted num">· {dateLabel(viewing.date)} · {inr(viewing.amount)}</span></span>
              <button className="btn btn-ghost btn-sm icon-btn" aria-label="Close" onClick={() => setViewing(null)}><X aria-hidden /></button>
            </div>
            <div className="viewer-body"><ReceiptImage id={viewing.receipt_id} alt={`Receipt from ${viewing.merchant}`} /></div>
          </>
        )}
      </dialog>
    </>
  );
}
