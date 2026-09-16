import { Navigate, NavLink, Route, Routes, Link, useLocation } from "react-router-dom";
import { LayoutGrid, ScanLine, BookOpen, PiggyBank, LogOut, Loader2 } from "lucide-react";
import { useAuth } from "./lib/auth";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Scan from "./pages/Scan";
import Expenses from "./pages/Expenses";
import Budgets from "./pages/Budgets";
import { Logo } from "./components/Logo";

function Shell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="wordmark" aria-label="SpendLens home">
            <Logo />
            <span className="wordmark-text">SpendLens</span>
          </Link>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end><LayoutGrid aria-hidden />Overview</NavLink>
            <NavLink to="/scan"><ScanLine aria-hidden />Scan</NavLink>
            <NavLink to="/expenses"><BookOpen aria-hidden />Expenses</NavLink>
            <NavLink to="/budgets"><PiggyBank aria-hidden />Budgets</NavLink>
          </nav>
          <div className="topbar-user">
            <span className="who">{user?.name}</span>
            <button className="btn btn-ghost btn-sm" onClick={logout} title="Sign out">
              <LogOut aria-hidden /> <span className="hide-sm">Sign out</span>
            </button>
          </div>
        </div>
      </header>
      <main className="page">{children}</main>
    </>
  );
}

function AfterLogin() {
  const next = (useLocation().state as { next?: string } | null)?.next;
  return <Navigate to={next ?? "/"} replace />;
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="page loading"><Loader2 className="spin" aria-hidden /> Loading…</div>;
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/scan" element={<Scan />} />
        <Route path="/expenses" element={<Expenses />} />
        <Route path="/budgets" element={<Budgets />} />
        <Route path="/login" element={<AfterLogin />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
