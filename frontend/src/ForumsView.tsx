import PersonaActivityView from "./PersonaActivityView";
import { MessageIcon } from "./icons";

// PS-26151 capability B: cross-platform persona mapping via real forum
// datasets only — evolution_forum and the DarkForums sample (ingested as
// darkforums_demo_overlay; see ARGUS_DATA_RESOURCES.md), both real historical
// data, no synthetic forum content.
const FORUM_PLATFORMS = ["evolution_forum", "darkforums_demo_overlay"];

const PLATFORM_LABELS: Record<string, string> = {
  evolution_forum: "Evolution Forum",
  darkforums_demo_overlay: "DarkForums Dataset",
};

export default function ForumsView({ onSelectActor }: { onSelectActor: (id: string) => void }) {
  return (
    <PersonaActivityView
      title="Forum Intelligence"
      description="Handles, PGP keys, and wallets observed across dark-web forum datasets, cross-referenced to Argus's actor clusters. Both sources are real historical data — no fabricated posts."
      icon={<MessageIcon width={16} height={16} />}
      platforms={FORUM_PLATFORMS}
      platformLabels={PLATFORM_LABELS}
      onSelectActor={onSelectActor}
    />
  );
}
