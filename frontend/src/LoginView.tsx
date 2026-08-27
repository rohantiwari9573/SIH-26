import { FormEvent, useState } from "react";
import { ApiError, login, register } from "./api";
import { AlertIcon, EyeIcon, LoaderIcon } from "./icons";

export default function LoginView({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "register") {
        await register(email, password);
      }
      await login(email, password);
      onLoggedIn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="centered">
      <form className="card" onSubmit={handleSubmit}>
        <div className="brand-mark" style={{ width: 44, height: 44, borderRadius: 12 }}>
          <EyeIcon width={22} height={22} />
        </div>

        <div>
          <h1>Argus</h1>
          <p className="subtitle">Dark Web Threat Actor Attribution</p>
        </div>

        <label>
          Email
          <input
            type="email"
            required
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            required
            minLength={8}
            maxLength={72}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {error && (
          <p className="error">
            <AlertIcon width={15} height={15} />
            {error}
          </p>
        )}

        <button type="submit" disabled={busy}>
          {busy && <LoaderIcon width={15} height={15} />}
          {busy ? "Working..." : mode === "login" ? "Log in" : "Register & log in"}
        </button>

        <button
          type="button"
          className="link-button"
          style={{ alignSelf: "center", marginTop: "0.25rem" }}
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "Need an account? Register" : "Already have an account? Log in"}
        </button>
      </form>
    </div>
  );
}
