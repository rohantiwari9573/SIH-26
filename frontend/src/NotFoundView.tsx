import { AlertIcon, EyeIcon } from "./icons";

export default function NotFoundView({ path }: { path: string }) {
  return (
    <div className="centered">
      <div className="card" style={{ maxWidth: 440, textAlign: "center", display: "flex", flexDirection: "column", gap: "1.1rem", alignItems: "center" }}>
        <div className="brand-mark" style={{ width: 44, height: 44, borderRadius: 12 }}>
          <EyeIcon width={22} height={22} />
        </div>

        <div>
          <h1>Page not found</h1>
          <p className="subtitle">
            <code>{path}</code> doesn't correspond to anything in Argus.
          </p>
        </div>

        <p className="error" style={{ justifyContent: "center" }}>
          <AlertIcon width={15} height={15} />
          Error 404
        </p>

        <button type="button" className="btn-primary" onClick={() => window.location.assign("/")}>
          Return to Argus
        </button>
      </div>
    </div>
  );
}
