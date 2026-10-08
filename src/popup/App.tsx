import { useEffect, useState } from "react";
import { MeetingStatus } from "./components/MeetingStatus";
import { CaptureToggle } from "./components/CaptureToggle";
import { AgendaEditor } from "./components/AgendaEditor";
import { useTheme } from "@/shared/hooks/useTheme";
import { useChromeState } from "@/shared/hooks/useChromeState";
import { CaptureState } from "@/types/meeting";
import type { BackgroundToContent, PopupToBackground } from "@/types/messages";
import "./popup.css";

type PopupView = "main" | "agenda";

/**
 * Minimal launcher. The full UI (agenda, hints, transcript, quick settings)
 * lives in the overlay injected into the Google Meet page.
 */
export function App() {
  useTheme();
  const { meetingStatus, captureState, meetingTitle, startTime, agendaItems, refresh } =
    useChromeState();
  const [view, setView] = useState<PopupView>("main");

  // Opening the popup brings back an overlay the user closed on the Meet tab.
  useEffect(() => {
    chrome.tabs
      .query({ active: true, currentWindow: true })
      .then(([tab]) => {
        if (tab?.id !== undefined) {
          chrome.tabs
            .sendMessage(tab.id, { type: "SHOW_OVERLAY" } satisfies BackgroundToContent)
            .catch(() => {});
        }
      })
      .catch(() => {});
  }, []);

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

  return (
    <div className="popup-container">
      <div className="popup-header">
        <div className="popup-logo">
          <div className="popup-logo-icon">M</div>
          <span className="popup-logo-text">Meeting Assistant</span>
        </div>
        <button
          className="popup-settings-btn"
          onClick={() => chrome.runtime.openOptionsPage()}
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

      <button
        className="popup-link-btn"
        onClick={() => setView("agenda")}
        disabled={isCapturing}
        title={isCapturing ? "Stop capture to edit the agenda" : undefined}
      >
        Edit agenda ({agendaItems.length})
      </button>

      <p className="capture-hint">
        Agenda, hints and transcript are shown in the panel on the Google Meet page.
      </p>
    </div>
  );
}
