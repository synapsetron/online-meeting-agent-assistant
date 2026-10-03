import { useState } from "react";
import { MeetingStatus } from "./components/MeetingStatus";
import { CaptureToggle } from "./components/CaptureToggle";
import { AgendaOverview } from "./components/AgendaOverview";
import { AgendaEditor } from "./components/AgendaEditor";
import { SettingsPanel } from "./components/SettingsPanel";
import { ConsentIndicator } from "./components/ConsentIndicator";
import { useTheme } from "@/shared/hooks/useTheme";
import { useChromeState } from "@/shared/hooks/useChromeState";
import { CaptureState } from "@/types/meeting";
import type { PopupToBackground } from "@/types/messages";
import "./popup.css";

type PopupView = "main" | "agenda" | "settings";

export function App() {
  useTheme();
  const { meetingStatus, captureState, meetingTitle, startTime, agendaItems, refresh } =
    useChromeState();
  const [view, setView] = useState<PopupView>("main");

  const isCapturing = captureState === CaptureState.Capturing;

  const handleToggleCapture = () => {
    chrome.runtime.sendMessage(
      { type: "TOGGLE_CAPTURE" } as PopupToBackground,
      () => refresh(),
    );
  };

  if (view === "agenda") {
    return (
      <div className="popup-container">
        <AgendaEditor onClose={() => { setView("main"); refresh(); }} />
      </div>
    );
  }

  if (view === "settings") {
    return (
      <div className="popup-container">
        <SettingsPanel onClose={() => setView("main")} />
      </div>
    );
  }

  return (
    <div className="popup-container">
      <div className="popup-header">
        <div className="popup-logo">
          <div className="popup-logo-icon">M</div>
          <span className="popup-logo-text">Meeting Assistant</span>
        </div>
        <button
          className="popup-settings-btn"
          onClick={() => setView("settings")}
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

      <AgendaOverview
        items={agendaItems}
        onEdit={isCapturing ? undefined : () => setView("agenda")}
      />

      <ConsentIndicator />
    </div>
  );
}
