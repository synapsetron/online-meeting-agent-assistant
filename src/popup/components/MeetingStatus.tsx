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
    <div className="meeting-status">
      <div
        className={`meeting-dot${status === MeetingStatusEnum.Connected ? " pulse" : ""}`}
        style={{ background: config.dot }}
      />
      <div className="meeting-info">
        <div className="meeting-title">
          {status === MeetingStatusEnum.Disconnected ? config.label : title}
        </div>
        {status === MeetingStatusEnum.Connected && (
          <div className="meeting-subtitle">
            {config.label} · {formatDuration(elapsed)}
          </div>
        )}
        {status === MeetingStatusEnum.Ended && (
          <div className="meeting-subtitle">
            Duration: {formatDuration(elapsed)}
          </div>
        )}
      </div>
    </div>
  );
}
