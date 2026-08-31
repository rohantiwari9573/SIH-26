import PersonaActivityView from "./PersonaActivityView";
import { StoreIcon } from "./icons";

// PS-26151 capability B: cross-platform threat-actor mapping. Reuses only
// existing sources — evolution_market is the real ingested marketplace
// dataset; mock_marketplace_1/2/3 are Argus's own synthetic/controlled data
// (labeled as such below, never conflated with real data).
const MARKETPLACE_PLATFORMS = [
  "evolution_market",
  "mock_marketplace_1",
  "mock_marketplace_2",
  "mock_marketplace_3",
];

const PLATFORM_LABELS: Record<string, string> = {
  evolution_market: "Evolution Market",
  mock_marketplace_1: "Mock Marketplace 1",
  mock_marketplace_2: "Mock Marketplace 2",
  mock_marketplace_3: "Mock Marketplace 3",
};

export default function MarketplacesView({
  onSelectActor,
}: {
  onSelectActor: (id: string) => void;
}) {
  return (
    <PersonaActivityView
      title="Marketplace Intelligence"
      description="Vendor and persona activity across dark-web marketplaces — handles, PGP keys, and wallets, cross-referenced to Argus's actor clusters. Evolution Market is a real ingested dataset; the Mock Marketplace sources are Argus's own synthetic/controlled data."
      icon={<StoreIcon width={16} height={16} />}
      platforms={MARKETPLACE_PLATFORMS}
      platformLabels={PLATFORM_LABELS}
      onSelectActor={onSelectActor}
    />
  );
}
