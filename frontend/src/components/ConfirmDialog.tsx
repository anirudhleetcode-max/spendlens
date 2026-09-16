import { useEffect, useRef } from "react";

type Props = {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
};

/** Native <dialog>: focus trap, Esc to cancel and backdrop come from the browser. */
export function ConfirmDialog({ open, title, body, confirmLabel, onConfirm, onCancel }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal?.();
    if (!open && d.open) d.close?.();
  }, [open]);
  return (
    <dialog ref={ref} className="viewer confirm" onClose={onCancel} aria-labelledby="confirm-title">
      {open && (
        <form method="dialog" onSubmit={(e) => { e.preventDefault(); onConfirm(); }}>
          <div className="viewer-body">
            <h2 id="confirm-title">{title}</h2>
            <p className="muted" style={{ marginTop: 8 }}>{body}</p>
          </div>
          <div className="form-actions" style={{ margin: 0, padding: "12px 16px" }}>
            <button type="button" className="btn" onClick={onCancel} autoFocus>Cancel</button>
            <button type="submit" className="btn btn-danger-solid">{confirmLabel}</button>
          </div>
        </form>
      )}
    </dialog>
  );
}
