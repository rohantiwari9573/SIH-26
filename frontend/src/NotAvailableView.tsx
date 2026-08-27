import { InboxIcon } from "./icons";

export default function NotAvailableView({ title, reason }: { title: string; reason: string }) {
  return (
    <div className="empty-state" style={{ margin: "3rem auto", maxWidth: 480 }}>
      <InboxIcon width={32} height={32} />
      <div>
        <strong>{title}</strong>
        <p className="muted" style={{ marginTop: "0.25rem" }}>
          {reason}
        </p>
      </div>
    </div>
  );
}
