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
import NotAvailableView from "./NotAvailableView";
import Sidebar from "./Sidebar";
import { EyeIcon, LogOutIcon, PlusIcon } from "./icons";

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
  | { name: "hidden-services" }
  | { name: "marketplaces" }
  | { name: "forums" }
  | { name: "alerts" }
  | { name: "reports" }
  | { name: "jobs" }
  | { name: "settings" };

const NOT_AVAILABLE_COPY: Partial<Record<View["name"], { title: string; reason: string }>> = {
  "hidden-services": {
    title: "Hidden Services",
    reason: "Covered today under Infrastructure findings on each actor's profile page; a dedicated cross-actor view isn't built yet.",
  },
  marketplaces: {
    title: "Marketplaces",
    reason: "See the \"Top Data Sources\" panel on the Dashboard for a real breakdown by source platform — a dedicated marketplace management page isn't built yet.",
  },
  forums: {
    title: "Forums",
    reason: "No forum-specific data source is connected yet.",
  },
  alerts: {
    title: "Alerts",
    reason: "No alerting engine exists yet — nothing here would be real.",
  },
  reports: {
    title: "Reports",
    reason: "Use \"Export CSV / JSON / Report\" on any actor's profile page — a dedicated report library isn't built yet.",
  },
  jobs: {
    title: "Jobs & Scans",
    reason: "Analysis jobs are tracked per-submission (poll /api/jobs/{task_id}) but there's no persisted job history to list yet.",
  },
  settings: {
    title: "Settings",
    reason: "No account/settings management is built yet beyond login and logout.",
  },
};

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
          {NOT_AVAILABLE_COPY[view.name] && (
            <NotAvailableView
              title={NOT_AVAILABLE_COPY[view.name]!.title}
              reason={NOT_AVAILABLE_COPY[view.name]!.reason}
            />
          )}
        </main>
      </div>
    </div>
  );
}
