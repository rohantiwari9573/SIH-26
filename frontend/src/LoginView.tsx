import { FormEvent, useId, useState } from "react";
import { ApiError, login, register } from "./api";
import { AlertIcon, ClipboardIcon, EyeIcon, EyeOffIcon, LinkIcon, LoaderIcon, NetworkIcon, ServerIcon } from "./icons";

const CAPABILITIES = [
  {
    icon: LinkIcon,
    title: "Actor Attribution",
    description: "Cross-platform handles, PGP keys and wallet correlation.",
  },
  {
    icon: ServerIcon,
    title: "Infrastructure Intelligence",
    description: "Hidden-service findings and clearnet infrastructure relationships.",
  },
  {
    icon: NetworkIcon,
    title: "Evidence Graph",
    description: "Investigate identifiers, relationships and provenance.",
  },
  {
    icon: ClipboardIcon,
    title: "Analytical Reporting",
    description: "Export attribution findings and investigative evidence.",
  },
];

/** Purely decorative — an abstract echo of the real relationship graph
 * (GraphView.tsx), never real data. No labels, no identifiers, no
 * fabricated statistics; see the login redesign brief's explicit
 * instruction not to expose or imply intelligence before authentication. */
function AuthGraphBackground() {
  const nodes: { x: number; y: number; r: number; glow?: boolean }[] = [
    { x: 120, y: 140, r: 4 },
    { x: 260, y: 90, r: 3 },
    { x: 340, y: 220, r: 5, glow: true },
    { x: 200, y: 300, r: 3 },
    { x: 460, y: 160, r: 4 },
    { x: 520, y: 320, r: 3 },
    { x: 380, y: 400, r: 5, glow: true },
    { x: 140, y: 420, r: 3 },
    { x: 560, y: 460, r: 4 },
    { x: 280, y: 500, r: 3 },
    { x: 440, y: 560, r: 5, glow: true },
    { x: 620, y: 240, r: 3 },
    { x: 90, y: 560, r: 3 },
    { x: 500, y: 620, r: 3 },
  ];
  const edges: [number, number][] = [
    [0, 1], [1, 2], [2, 3], [0, 3], [2, 4], [4, 5], [2, 6], [6, 7],
    [3, 7], [5, 8], [6, 9], [8, 10], [6, 10], [4, 11], [7, 12], [10, 13],
    [9, 12],
  ];

  return (
    <svg
      className="auth-graph-bg"
      viewBox="0 0 700 700"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      {edges.map(([a, b], i) => (
        <line
          key={i}
          x1={nodes[a].x}
          y1={nodes[a].y}
          x2={nodes[b].x}
          y2={nodes[b].y}
          className="auth-graph-edge"
        />
      ))}
      {nodes.map((n, i) => (
        <circle
          key={i}
          cx={n.x}
          cy={n.y}
          r={n.r}
          className={n.glow ? "auth-graph-node auth-graph-node-glow" : "auth-graph-node"}
        />
      ))}
    </svg>
  );
}

export default function LoginView({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const emailId = useId();
  const passwordId = useId();
  const errorId = useId();

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

  const isRegister = mode === "register";

  return (
    <div className="auth-shell">
      <div className="auth-intro">
        <AuthGraphBackground />
        <div className="auth-intro-content">
          <div className="brand">
            <div className="brand-mark" style={{ width: 40, height: 40, borderRadius: 11 }}>
              <EyeIcon width={20} height={20} />
            </div>
            <div className="brand-text">
              <h1 style={{ fontSize: "1.3rem" }}>Argus</h1>
              <span>Dark Web Threat Actor Attribution</span>
            </div>
          </div>

          <h2 className="auth-tagline">Investigate. Correlate. Attribute.</h2>
          <p className="auth-lede">
            Unify dark-web identities, infrastructure indicators and behavioral evidence into a
            single investigative graph.
          </p>

          <div className="capability-list">
            {CAPABILITIES.map(({ icon: Icon, title, description }) => (
              <div className="capability-item" key={title}>
                <div className="capability-icon">
                  <Icon width={16} height={16} />
                </div>
                <div>
                  <div className="capability-title">{title}</div>
                  <div className="capability-description">{description}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="auth-panel">
        <form className="card auth-card" onSubmit={handleSubmit} noValidate>
          <div className="brand-mark" style={{ width: 44, height: 44, borderRadius: 12 }}>
            <EyeIcon width={22} height={22} />
          </div>

          <div>
            <h1>{isRegister ? "Create your account" : "Welcome back"}</h1>
            <p className="subtitle">
              {isRegister
                ? "Register to begin your investigation."
                : "Sign in to continue your investigation."}
            </p>
          </div>

          <label htmlFor={emailId}>
            Email
            <input
              id={emailId}
              type="email"
              required
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-describedby={error ? errorId : undefined}
              aria-invalid={error ? true : undefined}
            />
          </label>
          <label htmlFor={passwordId}>
            Password
            <div className="password-input-wrap">
              <input
                id={passwordId}
                type={showPassword ? "text" : "password"}
                required
                minLength={8}
                maxLength={72}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-describedby={error ? errorId : undefined}
                aria-invalid={error ? true : undefined}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                aria-pressed={showPassword}
                tabIndex={0}
              >
                {showPassword ? <EyeOffIcon width={16} height={16} /> : <EyeIcon width={16} height={16} />}
              </button>
            </div>
          </label>

          {error && (
            <p className="error" id={errorId} role="alert">
              <AlertIcon width={15} height={15} />
              {error}
            </p>
          )}

          <button type="submit" disabled={busy}>
            {busy && <LoaderIcon width={15} height={15} />}
            {busy ? "Working..." : isRegister ? "Register & log in" : "Log in"}
          </button>

          <div className="auth-switch">
            <span className="muted">
              {isRegister ? "Already have an account?" : "Need an account?"}
            </span>
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setError(null);
                setMode(isRegister ? "login" : "register");
              }}
            >
              {isRegister ? "Log in" : "Register"}
            </button>
          </div>
        </form>
        <p className="auth-footer-note">Secure access to Argus Intelligence</p>
      </div>
    </div>
  );
}
