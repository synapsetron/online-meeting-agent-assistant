import { useState, useEffect } from "react";
import { MeetingStatus as MeetingStatusComponent } from "./components/MeetingStatus";
import { CaptureToggle } from "./components/CaptureToggle";
import { AgendaOverview } from "./components/AgendaOverview";
import { ConsentIndicator } from "./components/ConsentIndicator";
import { MeetingStatus, CaptureState } from "@/types/meeting";
import { AgendaItemStatus, type AgendaItem } from "@/types/agenda";
import "./popup.css";

const MOCK_AGENDA: AgendaItem[] = [
  { id: "1", title: "Project overview", status: AgendaItemStatus.Covered, estimatedMinutes: 5, elapsedSeconds: 312, evidence: [], order: 1 },
  { id: "2", title: "Architecture review", status: AgendaItemStatus.Active, estimatedMinutes: 10, elapsedSeconds: 445, evidence: [], order: 2 },
  { id: "3", title: "ASR integration", status: AgendaItemStatus.Pending, estimatedMinutes: 8, elapsedSeconds: 0, evidence: [], order: 3 },
  { id: "4", title: "Evaluation protocol", status: AgendaItemStatus.Pending, estimatedMinutes: 10, elapsedSeconds: 0, evidence: [], order: 4 },
  { id: "5", title: "Timeline & milestones", status: AgendaItemStatus.Pending, estimatedMinutes: 5, elapsedSeconds: 0, evidence: [], order: 5 },
  { id: "6", title: "Open questions", status: AgendaItemStatus.Pending, estimatedMinutes: 7, elapsedSeconds: 0, evidence: [], order: 6 },
];

export function App() {
  const [meetingStatus, setMeetingStatus] = useState(MeetingStatus.Connected);
  const [captureState, setCaptureState] = useState(CaptureState.Capturing);
  const [meetingTitle] = useState("Thesis progress meeting");
  const [startTime] = useState(Date.now() - 757_000);
  const [agendaItems] = useState(MOCK_AGENDA);

  const [isDark, setIsDark] = useState(
    window.matchMedia("(prefers-color-scheme: dark)").matches,
  );

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => setIsDark(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  const handleToggleCapture = () => {
    if (captureState === CaptureState.Capturing) {
      setCaptureState(CaptureState.Stopped);
      setMeetingStatus(MeetingStatus.Ended);
    } else {
      setCaptureState(CaptureState.Capturing);
      setMeetingStatus(MeetingStatus.Connected);
    }
  };

  const handleOpenSettings = () => {
    if (typeof chrome !== "undefined" && chrome.runtime?.openOptionsPage) {
      chrome.runtime.openOptionsPage();
    }
  };

  return (
    <div className="popup-container">
      <div className="popup-header">
        <div className="popup-logo">
          <div className="popup-logo-icon">M</div>
          <span className="popup-logo-text">Meeting Assistant</span>
        </div>
        <button
          className="popup-settings-btn"
          onClick={handleOpenSettings}
          aria-label="Settings"
          title="Settings"
        >
          ⚙
        </button>
      </div>

      <MeetingStatusComponent
        status={meetingStatus}
        title={meetingTitle}
        startTime={startTime}
      />

      <CaptureToggle
        captureState={captureState}
        onToggle={handleToggleCapture}
      />

      <AgendaOverview items={agendaItems} />

      <ConsentIndicator />
    </div>
  );
}
