import { useState } from "react";
import { isLoggedIn, logout } from "./api";
import LoginView from "./LoginView";
import SearchView from "./SearchView";
import ActorProfileView from "./ActorProfileView";
import SubmitLeadView from "./SubmitLeadView";
import { EyeIcon, LogOutIcon, PlusIcon } from "./icons";

type View = { name: "search" } | { name: "profile"; actorId: string } | { name: "submit" };

export default function App() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn());
  const [view, setView] = useState<View>({ name: "search" });

  if (!loggedIn) {
    return <LoginView onLoggedIn={() => setLoggedIn(true)} />;
  }

  function handleLogout() {
    logout();
    setLoggedIn(false);
    setView({ name: "search" });
  }

  return (
    <div className="app-shell">
      <header>
        <div className="brand">
          <div className="brand-mark">
            <EyeIcon width={18} height={18} />
          </div>
          <div className="brand-text">
            <h1>Argus</h1>
            <span>Threat Actor Attribution</span>
          </div>
        </div>
        <div className="actions">
          {view.name !== "submit" && (
            <button className="btn-secondary" onClick={() => setView({ name: "submit" })}>
              <PlusIcon width={16} height={16} />
              Submit lead
            </button>
          )}
          <button className="btn-ghost" onClick={handleLogout}>
            <LogOutIcon width={16} height={16} />
            Log out
          </button>
        </div>
      </header>

      <main>
        {view.name === "search" && (
          <SearchView onSelectActor={(actorId) => setView({ name: "profile", actorId })} />
        )}
        {view.name === "profile" && (
          <ActorProfileView actorId={view.actorId} onBack={() => setView({ name: "search" })} />
        )}
        {view.name === "submit" && <SubmitLeadView onDone={() => setView({ name: "search" })} />}
      </main>
    </div>
  );
}
