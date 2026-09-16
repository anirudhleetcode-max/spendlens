import { Plus, X } from "lucide-react";
import type { LineItem } from "../lib/types";
import { inr } from "../lib/format";

export function ItemsEditor({ items, onChange }: { items: LineItem[]; onChange: (items: LineItem[]) => void }) {
  const set = (i: number, patch: Partial<LineItem>) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const sum = items.reduce((s, it) => s + (Number(it.price) || 0), 0);
  return (
    <div className="table-scroll">
      <table className="ledger items-table">
        <thead>
          <tr><th>Item</th><th className="amt" style={{ width: 70 }}>Qty</th><th className="amt" style={{ width: 120 }}>Amount</th><th className="actions"><span className="visually-hidden">Remove</span></th></tr>
        </thead>
        <tbody>
          {items.length === 0 && (
            <tr><td colSpan={4} className="muted small">No line items. They're optional — add them if you want item-level search.</td></tr>
          )}
          {items.map((it, i) => (
            <tr key={i}>
              <td><input className="input" aria-label={`Item ${i + 1} name`} value={it.name} maxLength={80}
                onChange={(e) => set(i, { name: e.target.value })} /></td>
              <td><input className="input num" aria-label={`Item ${i + 1} quantity`} type="number" min={0} step="any" value={it.qty}
                onChange={(e) => set(i, { qty: Number(e.target.value) })} /></td>
              <td><input className="input num" aria-label={`Item ${i + 1} amount`} type="number" min={0} step="0.01" value={it.price}
                onChange={(e) => set(i, { price: Number(e.target.value) })} /></td>
              <td className="actions">
                <button type="button" className="btn btn-ghost btn-sm icon-btn btn-danger" aria-label={`Remove item ${i + 1}`}
                  onClick={() => onChange(items.filter((_, j) => j !== i))}><X aria-hidden /></button>
              </td>
            </tr>
          ))}
        </tbody>
        {items.length > 0 && (
          <tfoot><tr><td>Items total</td><td /><td className="amt num">{inr(sum)}</td><td /></tr></tfoot>
        )}
      </table>
      <button type="button" className="btn btn-sm btn-ghost" style={{ marginTop: 6 }}
        onClick={() => onChange([...items, { name: "", qty: 1, price: 0 }])}><Plus aria-hidden />Add item</button>
    </div>
  );
}
