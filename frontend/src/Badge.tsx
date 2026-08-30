/** Small provenance badges distinguishing real external intelligence from
 * controlled/synthetic Argus data — see docs/ETHICS.md. Never decorative:
 * each variant corresponds to a real, checkable distinction (a live-fetched
 * external source vs. a historical ingested dataset vs. Argus's own
 * synthetic demo identities). */
export type BadgeVariant = "live" | "historical" | "synthetic";

const LABELS: Record<BadgeVariant, string> = {
  live: "Live Source",
  historical: "Historical Source",
  synthetic: "Synthetic / Controlled",
};

export default function Badge({ variant, label }: { variant: BadgeVariant; label?: string }) {
  return <span className={`badge badge-${variant}`}>{label ?? LABELS[variant]}</span>;
}
