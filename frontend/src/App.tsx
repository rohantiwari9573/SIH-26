import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { isLoggedIn, logout } from "./api";
import LoginView from "./LoginView";
import NotFoundView from "./NotFoundView";
import DashboardView from "./DashboardView";
import Sidebar from "./Sidebar";
import { EyeIcon, LoaderIcon, LogOutIcon, PlusIcon } from "./icons";

// Dashboard loads eagerly (it's the screen every session lands on right
// after login); every other view is only ever needed once a user clicks
// into it, so they're code-split into their own chunks rather than
// bundled into the initial JS payload.
const SearchView = lazy(() => import("./SearchView"));
const ActorProfileView = lazy(() => import("./ActorProfileView"));
const SubmitLeadView = lazy(() => import("./SubmitLeadView"));
const InfrastructureView = lazy(() => import("./InfrastructureView"));
const IndicatorsView = lazy(() => import("./IndicatorsView"));
const TimelineView = lazy(() => import("./TimelineView"));
const AttributionView = lazy(() => import("./AttributionView"));
const SourcesView = lazy(() => import("./SourcesView"));
const DemoScenarioView = lazy(() => import("./DemoScenarioView"));
const HiddenServicesView = lazy(() => import("./HiddenServicesView"));
const MarketplacesView = lazy(() => import("./MarketplacesView"));
const ForumsView = lazy(() => import("./ForumsView"));
const AlertsView = lazy(() => import("./AlertsView"));
const ReportsView = lazy(() => import("./ReportsView"));
const JobsScansView = lazy(() => import("./JobsScansView"));

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
  // The app never changes window.location.pathname itself (in-app
  // navigation only pushes history *state*, not a new URL — see the
  // pushState call below), so a one-time check of the path this document
  // actually loaded at is enough to tell "real Argus URL" from "unknown
  // path someone typed/linked to" for the whole session.
  const [invalidPath] = useState<string | null>(() => {
    const p = window.location.pathname;
    return p === "/" ? null : p;
  });
  // The app has no URL routing (view lives only in React state), so the
  // browser's own history stack never gets an entry per screen. Without
  // this, pressing the physical/gesture Back button has nothing of ours to
  // undo and falls through to whatever page was open *before* Argus was
  // ever loaded — which reads as the app randomly disappearing/"logging
  // out". Treating Dashboard as the root history entry and pushing one
  // entry per navigation makes Back/Forward move within the app instead.
  const isPoppingRef = useRef(false);

  useEffect(() => {
    window.history.replaceState({ view: { name: "dashboard" } as View }, "");
    function onPopState(event: PopStateEvent) {
      isPoppingRef.current = true;
      setView((event.state?.view as View | undefined) ?? { name: "dashboard" });
      isPoppingRef.current = false;
    }
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  function navigate(next: View) {
    setView(next);
    // A popstate-triggered update is the browser already moving through
    // its own history — pushing another entry here would double up and
    // break Back (it would just re-arrive at the same screen).
    if (!isPoppingRef.current) {
      window.history.pushState({ view: next }, "");
    }
  }

  if (invalidPath) {
    return <NotFoundView path={invalidPath} />;
  }

  if (!loggedIn) {
    return <LoginView onLoggedIn={() => setLoggedIn(true)} />;
  }

  function handleLogout() {
    logout();
    setLoggedIn(false);
    setView({ name: "dashboard" });
    window.history.replaceState({ view: { name: "dashboard" } as View }, "");
  }

  function selectActor(actorId: string) {
    navigate({ name: "profile", actorId });
  }

  function handleNav(name: View["name"]) {
    navigate({ name } as View);
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
            <button className="btn-secondary" onClick={() => navigate({ name: "submit" })}>
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
          <Suspense
            fallback={
              <div className="centered" style={{ minHeight: "auto", padding: "4rem 0" }}>
                <LoaderIcon width={20} height={20} />
              </div>
            }
          >
          {view.name === "dashboard" && <DashboardView onSelectActor={selectActor} />}
          {view.name === "search" && <SearchView onSelectActor={selectActor} />}
          {view.name === "profile" && (
            <ActorProfileView actorId={view.actorId} onBack={() => navigate({ name: "search" })} />
          )}
          {view.name === "submit" && <SubmitLeadView onDone={() => navigate({ name: "search" })} />}
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
          </Suspense>
        </main>
      </div>
    </div>
  );
}
