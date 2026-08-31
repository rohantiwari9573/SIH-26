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
 * instruction not to expose or imply intelligence before authentication.
 *
 * The layout isn't random noise: it loosely reads as a left-to-right(ish)
 * investigative pipeline — a small "sources" cluster feeding into
 * "identifiers", funneling through a "relationships" hub, converging on
 * an "attribution" node positioned down toward the capability-card area
 * — without ever labeling a single node, so it stays honestly abstract. */
function AuthGraphBackground() {
  const nodes: { x: number; y: number; r: number; glow?: boolean; delay?: number }[] = [
    // sources — small cluster, upper right, away from the headline text
    { x: 560, y: 58, r: 3 },
    { x: 630, y: 128, r: 4, glow: true, delay: 0 },
    { x: 498, y: 30, r: 2.5 },
    // identifiers — funnels down-left from the source cluster
    { x: 520, y: 198, r: 3.5 },
    { x: 612, y: 248, r: 3 },
    { x: 448, y: 138, r: 3 },
    // relationships — the busiest hub, largest anchor
    { x: 418, y: 298, r: 6, glow: true, delay: 1.7 },
    { x: 560, y: 356, r: 3 },
    { x: 330, y: 236, r: 3 },
    // attribution — final convergence, near the capability cards below
    { x: 296, y: 458, r: 5.5, glow: true, delay: 3.2 },
    { x: 408, y: 536, r: 3.5 },
    { x: 188, y: 536, r: 3 },
    { x: 140, y: 606, r: 2.5 },
  ];
  const edges: [number, number][] = [
    [0, 1], [1, 2], [0, 2],
    [2, 5], [1, 4], [0, 3],
    [3, 5],
    [5, 8], [3, 6], [4, 7],
    [6, 8], [6, 7],
    [6, 9], [7, 10], [8, 11],
    [9, 10], [9, 11], [11, 12],
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
          style={n.glow ? { animationDelay: `${n.delay}s` } : undefined}
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
