import { useEffect, useState } from "react";
import { clearAuthSession, getAuthRole, getAuthToken, getAuthUser, setAuthSession } from "../services/auth.js";
import { loginOperator } from "../services/api.js";

/** Optional only — private demo does not require login. */
export default function OperatorSession() {
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("operator");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState(() => getAuthToken());
  const [role, setRole] = useState(() => getAuthRole());
  const [user, setUser] = useState(() => getAuthUser());

  useEffect(() => {
    const sync = () => {
      setToken(getAuthToken());
      setRole(getAuthRole());
      setUser(getAuthUser());
    };
    window.addEventListener("voyamind-auth", sync);
    return () => window.removeEventListener("voyamind-auth", sync);
  }, []);

  async function onLogin(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await loginOperator(username, password);
      if (!res?.access_token) throw new Error(res?.detail || "Login failed");
      setAuthSession(res);
      setOpen(false);
      setPassword("");
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || "Login failed";
      setError(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally {
      setBusy(false);
    }
  }

  if (token) {
    return (
      <div className="operator-session signed-in">
        <span className="badge live">{role || "AUTH"}</span>
        <span className="muted session-user">{user}</span>
        <button type="button" className="ghost-btn" onClick={() => clearAuthSession()}>
          Sign out
        </button>
      </div>
    );
  }

  return (
    <div className="operator-session">
      <span className="muted" style={{ fontSize: 11 }}>
        Private demo · auth off
      </span>
      <button type="button" className="ghost-btn" onClick={() => setOpen((v) => !v)}>
        Optional login
      </button>
      {open ? (
        <form className="operator-login-popover glass-elevated" onSubmit={onLogin}>
          <p className="hint">Optional — RUN SCENARIO / HQRL work without signing in.</p>
          <label>
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          {error ? <p className="error-text">{error}</p> : null}
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      ) : null}
    </div>
  );
}
