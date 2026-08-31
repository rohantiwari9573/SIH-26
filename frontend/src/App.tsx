import { useState } from "react";
import { isLoggedIn, logout } from "./api";
import LoginView from "./LoginView";
import SearchView from "./SearchView";
import ActorProfileView from "./ActorProfileView";
import SubmitLeadView from "./SubmitLeadView";
import DashboardView from "./DashboardView";
import InfrastructureView from "./InfrastructureView";
import IndicatorsView from "./IndicatorsView";
import TimelineView from "./TimelineView";
import AttributionView from "./AttributionView";
import SourcesView from "./SourcesView";
import DemoScenarioView from "./DemoScenarioView";
import HiddenServicesView from "./HiddenServicesView";
import MarketplacesView from "./MarketplacesView";
import ForumsView from "./ForumsView";
import AlertsView from "./AlertsView";
import ReportsView from "./ReportsView";
import JobsScansView from "./JobsScansView";
import Sidebar from "./Sidebar";
import { EyeIcon, LogOutIcon, PlusIcon } from "./icons";

// Settings was deliberately removed rather than implemented: Argus has no
// persisted, user-configurable application setting anywhere (API keys and
// graph defaults are env/code-level, not DB-backed), so a Settings page
// would only ever hold meaningless toggles — see the Phase 5 audit notes.
export type View =
  | { name: "dashboard" }
  | { name: "search" }
  | { name: "profile"; actorId: string }
  | { name: "submit" }
  | { name: "infrastructure" }
  | { name: "attribution" }
  | { name: "timeline" }
  | { name: "indicators" }
  | { name: "sources" }
  | { name: "demo" }
  | { name: "hidden-services" }
  | { name: "marketplaces" }
  | { name: "forums" }
  | { name: "alerts" }
  | { name: "reports" }
  | { name: "jobs" };

export default function App() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn());
  const [view, setView] = useState<View>({ name: "dashboard" });

  if (!loggedIn) {
    return <LoginView onLoggedIn={() => setLoggedIn(true)} />;
  }

  function handleLogout() {
    logout();
    setLoggedIn(false);
    setView({ name: "dashboard" });
  }

  function selectActor(actorId: string) {
    setView({ name: "profile", actorId });
  }

  function handleNav(name: View["name"]) {
    setView({ name } as View);
  }

  return (
    <div className="app-shell app-shell-sidebar">
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

      <div className="app-body">
        <Sidebar active={view.name} onSelect={handleNav} />
        <main>
          {view.name === "dashboard" && <DashboardView onSelectActor={selectActor} />}
          {view.name === "search" && <SearchView onSelectActor={selectActor} />}
          {view.name === "profile" && (
            <ActorProfileView actorId={view.actorId} onBack={() => setView({ name: "search" })} />
          )}
          {view.name === "submit" && <SubmitLeadView onDone={() => setView({ name: "search" })} />}
          {view.name === "infrastructure" && <InfrastructureView />}
          {view.name === "attribution" && <AttributionView onSelectActor={selectActor} />}
          {view.name === "timeline" && <TimelineView onSelectActor={selectActor} />}
          {view.name === "indicators" && <IndicatorsView />}
          {view.name === "sources" && <SourcesView />}
          {view.name === "demo" && <DemoScenarioView onSelectActor={selectActor} />}
          {view.name === "hidden-services" && <HiddenServicesView onSelectActor={selectActor} />}
          {view.name === "marketplaces" && <MarketplacesView onSelectActor={selectActor} />}
          {view.name === "forums" && <ForumsView onSelectActor={selectActor} />}
          {view.name === "alerts" && <AlertsView onSelectActor={selectActor} />}
          {view.name === "reports" && <ReportsView onSelectActor={selectActor} />}
          {view.name === "jobs" && <JobsScansView />}
        </main>
      </div>
    </div>
  );
}
