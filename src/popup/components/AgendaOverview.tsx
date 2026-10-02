import { AgendaItemStatus, type AgendaItem } from "@/types/agenda";

interface Props {
  items: AgendaItem[];
}

const STATUS_STYLES: Record<
  AgendaItemStatus,
  { bg: string; border: string; icon: string; color: string }
> = {
  [AgendaItemStatus.Pending]: { bg: "transparent", border: "var(--ma-border)", icon: "", color: "var(--ma-text-tertiary)" },
  [AgendaItemStatus.Active]: { bg: "var(--ma-accent)", border: "var(--ma-accent)", icon: "▶", color: "white" },
  [AgendaItemStatus.Covered]: { bg: "var(--ma-success)", border: "var(--ma-success)", icon: "✓", color: "white" },
  [AgendaItemStatus.Deferred]: { bg: "transparent", border: "var(--ma-warning)", icon: "↻", color: "var(--ma-warning)" },
  [AgendaItemStatus.Skipped]: { bg: "var(--ma-text-tertiary)", border: "var(--ma-text-tertiary)", icon: "—", color: "white" },
};

function progressClass(status: AgendaItemStatus): string {
  if (status === AgendaItemStatus.Covered) return "agenda-progress-seg covered";
  if (status === AgendaItemStatus.Active) return "agenda-progress-seg active";
  if (status === AgendaItemStatus.Deferred) return "agenda-progress-seg deferred";
  if (status === AgendaItemStatus.Skipped) return "agenda-progress-seg skipped";
  return "agenda-progress-seg";
}

export function AgendaOverview({ items }: Props) {
  const covered = items.filter((i) => i.status === AgendaItemStatus.Covered).length;

  return (
    <div className="agenda-section">
      <div className="agenda-header">
        <span className="agenda-label">Agenda</span>
        <span className="agenda-badge">{covered}/{items.length}</span>
      </div>

      <div className="agenda-progress">
        {items.map((item) => (
          <div key={item.id} className={progressClass(item.status)} />
        ))}
      </div>

      <div className="agenda-list">
        {items.map((item) => {
          const style = STATUS_STYLES[item.status];
          return (
            <div
              key={item.id}
              className={`agenda-item${item.status === AgendaItemStatus.Active ? " active" : ""}`}
            >
              <div
                className="agenda-icon"
                style={{
                  border: `2px solid ${style.border}`,
                  background: style.bg,
                  color: style.color,
                }}
              >
                {style.icon}
              </div>
              <span
                className={`agenda-item-title${item.status === AgendaItemStatus.Skipped ? " skipped" : ""}`}
              >
                {item.title}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
