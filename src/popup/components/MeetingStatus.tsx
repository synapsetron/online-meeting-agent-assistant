import { useState, useEffect } from "react";
import { MeetingStatus as MeetingStatusEnum } from "@/types/meeting";

interface Props {
  status: MeetingStatusEnum;
  title: string;
  startTime: number;
}

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0)
    return `${h}h ${(m % 60).toString().padStart(2, "0")}m`;
  return `${m}m ${(s % 60).toString().padStart(2, "0")}s`;
}

const STATUS_CONFIG = {
  [MeetingStatusEnum.Connected]: { dot: "#10b981", label: "Connected" },
  [MeetingStatusEnum.Connecting]: { dot: "#f59e0b", label: "Connecting..." },
  [MeetingStatusEnum.Disconnected]: { dot: "#9ca3af", label: "No active meeting" },
  [MeetingStatusEnum.Ended]: { dot: "#6b7280", label: "Meeting ended" },
};

export function MeetingStatus({ status, title, startTime }: Props) {
  const [elapsed, setElapsed] = useState(() => Date.now() - startTime);
  const config = STATUS_CONFIG[status];

  useEffect(() => {
    if (status !== MeetingStatusEnum.Connected) return;
    const timer = setInterval(() => setElapsed(Date.now() - startTime), 1000);
    return () => clearInterval(timer);
  }, [status, startTime]);

  return (
    <div style={{ padding: "12px 16px", display: "flex", alignItems: "center", gap: 10 }}>
      <div
        style={{
          width: 10,
          height: 10,
          borderRadius: "50%",
          background: config.dot,
          flexShrink: 0,
          animation: status === MeetingStatusEnum.Connected ? "pulse 2s ease-in-out infinite" : "none",
        }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 14,
            fontWeight: 600,
            color: "var(--popup-text)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {status === MeetingStatusEnum.Disconnected ? config.label : title}
        </div>
        {status === MeetingStatusEnum.Connected && (
          <div style={{ fontSize: 12, color: "var(--popup-text-secondary)" }}>
            {config.label} · {formatDuration(elapsed)}
          </div>
        )}
        {status === MeetingStatusEnum.Ended && (
          <div style={{ fontSize: 12, color: "var(--popup-text-secondary)" }}>
            Duration: {formatDuration(elapsed)}
          </div>
        )}
      </div>
    </div>
  );
}
