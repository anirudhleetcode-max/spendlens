import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Loader2 } from "lucide-react";
import { useAuth } from "../lib/auth";
import { Logo } from "../components/Logo";

export default function Login() {
  const { login, register } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // App swaps to the signed-in routes as soon as the user is set; /login then redirects to `next`
      nav("/login", { replace: true, state: { next: mode === "register" ? "/scan" : "/" } });
      if (mode === "login") await login(email, password);
      else await register(name, email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <aside className="auth-side">
        <div className="wordmark">
          <Logo light />
          <span className="wordmark-text">SpendLens</span>
        </div>
        <blockquote>Photograph the bill. Check two numbers. Know where the month went.</blockquote>
        <div className="auth-sample" aria-hidden>
          <div className="line"><span>DMart · Groceries</span><span>₹1,284.00</span></div>
          <div className="line"><span>Indian Oil · Fuel</span><span>₹750.00</span></div>
          <div className="line"><span>Apollo Pharmacy · Health</span><span>₹184.00</span></div>
        </div>
      </aside>
      <main className="auth-main">
        <div className="auth-card">
          <h1>{mode === "login" ? "Sign in" : "Create your ledger"}</h1>
          <p className="muted" style={{ marginTop: 6 }}>
            {mode === "login" ? "Receipts in, categorised expenses out." : "Takes ten seconds. No card details, no bank linking."}
          </p>
          <form onSubmit={submit}>
            {mode === "register" && (
              <label className="field">
                <span>Your name</span>
                <input className="input" name="name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={60} autoComplete="name" />
              </label>
            )}
            <label className="field">
              <span>Email</span>
              <input className="input" name="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
            </label>
            <label className="field">
              <span>Password {mode === "register" && <span className="conf">6+ characters</span>}</span>
              <input className="input" name="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                required minLength={6} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            </label>
            {error && <div className="notice error" role="alert"><AlertTriangle aria-hidden />{error}</div>}
            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy && <Loader2 className="spin" aria-hidden />}
              {mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>
          <div className="auth-switch">
            <button className="linklike" type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>
              {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
            </button>
            {mode === "login" && (
              <button className="linklike" type="button" onClick={() => { setEmail("demo@spendlens.app"); setPassword("demo1234"); }}>
                Use demo account
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
