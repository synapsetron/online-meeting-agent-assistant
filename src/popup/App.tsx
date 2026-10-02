import { MeetingStatus } from "./components/MeetingStatus";
import { CaptureToggle } from "./components/CaptureToggle";
import { AgendaOverview } from "./components/AgendaOverview";
import { ConsentIndicator } from "./components/ConsentIndicator";
import { useTheme } from "@/shared/hooks/useTheme";
import { useChromeState } from "@/shared/hooks/useChromeState";
import type { PopupToBackground } from "@/types/messages";
import "./popup.css";

export function App() {
  useTheme();
  const { meetingStatus, captureState, meetingTitle, startTime, agendaItems, refresh } =
    useChromeState();

  const handleToggleCapture = () => {
    chrome.runtime.sendMessage(
      { type: "TOGGLE_CAPTURE" } as PopupToBackground,
      () => refresh(),
    );
  };

  const handleOpenSettings = () => {
    if (chrome.runtime?.openOptionsPage) {
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

      <MeetingStatus
        status={meetingStatus}
        title={meetingTitle || "Meeting"}
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
