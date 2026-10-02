import { AgendaItemStatus, type AgendaItem } from "@/types/agenda";

interface Props {
  items: AgendaItem[];
}

const STATUS_STYLES: Record<
  AgendaItemStatus,
  { bg: string; border: string; icon: string; color: string }
> = {
  [AgendaItemStatus.Pending]: { bg: "transparent", border: "var(--popup-border)", icon: "", color: "var(--popup-text-tertiary)" },
  [AgendaItemStatus.Active]: { bg: "var(--popup-accent)", border: "var(--popup-accent)", icon: "▶", color: "white" },
  [AgendaItemStatus.Covered]: { bg: "var(--popup-success)", border: "var(--popup-success)", icon: "✓", color: "white" },
  [AgendaItemStatus.Deferred]: { bg: "transparent", border: "var(--popup-warning)", icon: "↻", color: "var(--popup-warning)" },
  [AgendaItemStatus.Skipped]: { bg: "var(--popup-text-tertiary)", border: "var(--popup-text-tertiary)", icon: "—", color: "white" },
};

export function AgendaOverview({ items }: Props) {
  const covered = items.filter((i) => i.status === AgendaItemStatus.Covered).length;

  return (
    <div style={{ padding: "12px 16px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 8,
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: 0.5,
            color: "var(--popup-text-secondary)",
          }}
        >
          Agenda
        </span>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: "var(--popup-text-secondary)",
            padding: "1px 7px",
            background: "var(--popup-bg-tertiary)",
            borderRadius: 10,
          }}
        >
          {covered}/{items.length}
        </span>
      </div>

      {/* Progress bar */}
      <div style={{ display: "flex", gap: 2, marginBottom: 8, height: 3 }}>
        {items.map((item) => (
          <div
            key={item.id}
            style={{
              flex: 1,
              borderRadius: 2,
              background:
                item.status === AgendaItemStatus.Covered
                  ? "var(--popup-success)"
                  : item.status === AgendaItemStatus.Active
                    ? "var(--popup-accent)"
                    : item.status === AgendaItemStatus.Deferred
                      ? "var(--popup-warning)"
                      : item.status === AgendaItemStatus.Skipped
                        ? "var(--popup-text-tertiary)"
                        : "var(--popup-border)",
            }}
          />
        ))}
      </div>

      {/* Item list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {items.map((item) => {
          const style = STATUS_STYLES[item.status];
          return (
            <div
              key={item.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "4px 6px",
                borderRadius: 6,
                background:
                  item.status === AgendaItemStatus.Active
                    ? "var(--popup-accent-light)"
                    : "transparent",
              }}
            >
              <div
                style={{
                  width: 16,
                  height: 16,
                  borderRadius: "50%",
                  border: `2px solid ${style.border}`,
                  background: style.bg,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 9,
                  color: style.color,
                  flexShrink: 0,
                }}
              >
                {style.icon}
              </div>
              <span
                style={{
                  flex: 1,
                  fontSize: 13,
                  color: "var(--popup-text)",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  textDecoration:
                    item.status === AgendaItemStatus.Skipped
                      ? "line-through"
                      : "none",
                  opacity:
                    item.status === AgendaItemStatus.Skipped ? 0.5 : 1,
                }}
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
