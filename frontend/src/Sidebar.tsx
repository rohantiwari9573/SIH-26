import {
  ActivityIcon,
  ClipboardIcon,
  ClockIcon,
  FlagIcon,
  GlobeIcon,
  GridIcon,
  LinkIcon,
  MessageIcon,
  NetworkIcon,
  PlayIcon,
  RssIcon,
  ServerIcon,
  StoreIcon,
  UserIcon,
} from "./icons";
import type { View } from "./App";

interface NavItem {
  key: View["name"];
  label: string;
  icon: JSX.Element;
  /** Every item is currently backed by a real, working view — kept as a
   * gate rather than removed so a future item with no honest data behind
   * it still has somewhere to degrade to instead of pretending to be live. */
  available: boolean;
}

const INVESTIGATION: NavItem[] = [
  { key: "dashboard", label: "Dashboard", icon: <GridIcon width={17} height={17} />, available: true },
  { key: "search", label: "Threat Actors", icon: <UserIcon width={17} height={17} />, available: true },
  { key: "infrastructure", label: "Infrastructure", icon: <ServerIcon width={17} height={17} />, available: true },
  { key: "attribution", label: "AI Attribution", icon: <LinkIcon width={17} height={17} />, available: true },
  { key: "timeline", label: "Timeline Explorer", icon: <ClockIcon width={17} height={17} />, available: true },
];

const COLLECTION: NavItem[] = [
  { key: "sources", label: "Sources & Feeds", icon: <RssIcon width={17} height={17} />, available: true },
  { key: "hidden-services", label: "Hidden Services", icon: <GlobeIcon width={17} height={17} />, available: true },
  { key: "marketplaces", label: "Marketplaces", icon: <StoreIcon width={17} height={17} />, available: true },
  { key: "forums", label: "Forums", icon: <MessageIcon width={17} height={17} />, available: true },
];

const INTELLIGENCE: NavItem[] = [
  { key: "alerts", label: "Alerts", icon: <FlagIcon width={17} height={17} />, available: true },
  { key: "indicators", label: "Indicators", icon: <NetworkIcon width={17} height={17} />, available: true },
  { key: "reports", label: "Reports", icon: <ClipboardIcon width={17} height={17} />, available: true },
  { key: "demo", label: "Controlled Demo", icon: <PlayIcon width={17} height={17} />, available: true },
];

const SYSTEM: NavItem[] = [
  { key: "jobs", label: "Jobs & Scans", icon: <ActivityIcon width={17} height={17} />, available: true },
];

function Section({
  title,
  items,
  active,
  onSelect,
}: {
  title: string;
  items: NavItem[];
  active: View["name"];
  onSelect: (key: View["name"]) => void;
}) {
  return (
    <div className="sidebar-section">
      <div className="sidebar-section-title">{title}</div>
      {items.map((item) => (
        <button
          key={item.key}
          className={`sidebar-item ${active === item.key ? "active" : ""} ${
            item.available ? "" : "sidebar-item-muted"
          }`}
          onClick={() => onSelect(item.key)}
        >
          {item.icon}
          <span>{item.label}</span>
          {!item.available && <span className="sidebar-badge">soon</span>}
        </button>
      ))}
    </div>
  );
}

export default function Sidebar({
  active,
  onSelect,
}: {
  active: View["name"];
  onSelect: (key: View["name"]) => void;
}) {
  return (
    <nav className="sidebar">
      <Section title="Investigation" items={INVESTIGATION} active={active} onSelect={onSelect} />
      <Section title="Collection" items={COLLECTION} active={active} onSelect={onSelect} />
      <Section title="Intelligence" items={INTELLIGENCE} active={active} onSelect={onSelect} />
      <Section title="System" items={SYSTEM} active={active} onSelect={onSelect} />
    </nav>
  );
}
