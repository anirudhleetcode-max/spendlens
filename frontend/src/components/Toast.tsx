import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, X } from "lucide-react";

type Toast = { id: number; kind: "ok" | "error"; text: string };
type Ctx = { notify: (text: string, kind?: Toast["kind"]) => void };

const ToastCtx = createContext<Ctx>({ notify: () => undefined });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const notify = useCallback((text: string, kind: Toast["kind"] = "ok") => {
    const id = next.current++;
    setToasts((t) => [...t.slice(-2), { id, kind, text }]);
    window.setTimeout(() => dismiss(id), kind === "error" ? 6000 : 3500);
  }, [dismiss]);
  return (
    <ToastCtx.Provider value={{ notify }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.kind === "ok" ? <CheckCircle2 aria-hidden /> : <AlertTriangle aria-hidden />}
            <span>{t.text}</span>
            <button className="btn btn-ghost btn-sm icon-btn" aria-label="Dismiss" onClick={() => dismiss(t.id)}><X aria-hidden /></button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export const useToast = () => useContext(ToastCtx);
