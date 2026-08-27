import { useState } from "react";
import { isLoggedIn, logout } from "./api";
import LoginView from "./LoginView";
import SearchView from "./SearchView";
import ActorProfileView from "./ActorProfileView";
import SubmitLeadView from "./SubmitLeadView";

type View =
  | { name: "search" }
  | { name: "profile"; actorId: string }
  | { name: "submit" };

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
        <h1>SIH26151 — Actor Attribution</h1>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          {view.name !== "submit" && (
            <button onClick={() => setView({ name: "submit" })}>+ Submit lead</button>
          )}
          <button className="link-button" onClick={handleLogout}>
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
        {view.name === "submit" && (
          <SubmitLeadView onDone={() => setView({ name: "search" })} />
        )}
      </main>
    </div>
  );
}
