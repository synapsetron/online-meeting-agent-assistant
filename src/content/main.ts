import { ShadowHost } from "./shadow-host";
import { OverlayContainer } from "./components/OverlayContainer";
import { ThemeManager } from "./components/ThemeManager";
import { MeetCaptionObserver } from "@/shared/meet-captions";
import { CaptureState } from "@/types/meeting";
import type { BackgroundToContent, ContentToBackground, PopupToBackground } from "@/types/messages";
import { resolveLocalUserName } from "@/shared/meet-user";
import { getMeetingCode, observeCallState } from "@/shared/meet-detector";

let disconnectObserver: (() => void) | null = null;
let host: ShadowHost | null = null;
let overlay: OverlayContainer | null = null;
let theme: ThemeManager | null = null;
let captionObserver: MeetCaptionObserver | null = null;

function sendToBackground(msg: ContentToBackground | PopupToBackground): void {
  try {
    chrome.runtime.sendMessage(msg).catch(() => {});
  } catch {
    // Extension context invalidated after update — ignore
  }
}

/**
 * Transcription comes from Google Meet's own captions for every participant,
 * the local user included: Meet uses the microphone selected in the call and
 * respects mute, and one source means no duplicated speech.
 */
function startRecognition() {
  if (captionObserver) {
    captionObserver.stop();
  }

  captionObserver = new MeetCaptionObserver();
  captionObserver.setSkipLocalUser(false);

  chrome.runtime.sendMessage({ type: "GET_STATE" } as PopupToBackground).then((response) => {
    if (response?.meeting?.id) {
      captionObserver?.setMeetingId(response.meeting.id);
    }
  }).catch(() => {});

  applyLocalUserName();

  captionObserver.onCaption((segment) => {
    overlay?.addTranscript(segment);
    sendToBackground({ type: "TRANSCRIPT_SEGMENT", segment });
  });

  captionObserver.start();
  captionObserver.tryEnableCaptions();

  console.log("[Meeting Assistant] Caption observer started");
}

/** Meet may render the account name late, so retry for a short while. */
function applyLocalUserName(attempt = 0) {
  resolveLocalUserName().then((name) => {
    if (name) {
      captionObserver?.setLocalUserName(name);
      console.log("[Meeting Assistant] Local user name resolved");
    } else if (attempt < 10 && captionObserver) {
      setTimeout(() => applyLocalUserName(attempt + 1), 3000);
    }
  });
}

function stopRecognition() {
  if (captionObserver) {
    captionObserver.stop();
    captionObserver = null;
    console.log("[Meeting Assistant] Caption observer stopped");
  }
}

function initOverlay() {
  if (host) {
    return;
  }

  host = new ShadowHost("open");

  overlay = new OverlayContainer({
    onDismissHint: (hintId) => {
      sendToBackground({ type: "DISMISS_HINT", hintId });
    },
    onStopCapture: () => {
      stopRecognition();
      overlay?.setCaptureState(CaptureState.Stopped);
      overlay?.showSummaryPending();
      sendToBackground({ type: "TOGGLE_CAPTURE" } as PopupToBackground);
    },
    onStartCapture: () => {
      sendToBackground({ type: "TOGGLE_CAPTURE" } as PopupToBackground);
    },
  });

  host.mount(overlay.root);

  theme = new ThemeManager(host.host);
  theme.init();

  chrome.runtime.onMessage.addListener(
    (message: BackgroundToContent, _sender, sendResponse) => {
      switch (message.type) {
        case "STATE_UPDATE":
          overlay?.setCaptureState(message.meeting.captureState, message.meeting.startTime);
          overlay?.updateAgenda(message.agenda);
          if (message.hints) {
            for (const hint of message.hints) {
              if (!hint.dismissed) {
                overlay?.addHint(hint);
              }
            }
          }
          if (message.recentTranscript) {
            for (const segment of message.recentTranscript) {
              overlay?.addTranscript(segment);
            }
          }
          break;

        case "NEW_TRANSCRIPT":
          console.log("[Meeting Assistant] NEW_TRANSCRIPT from backend:", message.segment.text?.substring(0, 50));
          overlay?.addTranscript(message.segment);
          break;

        case "SHOW_OVERLAY":
          overlay?.show();
          break;

        case "NEW_HINT":
          overlay?.addHint(message.hint);
          break;

        case "AGENDA_UPDATE":
          overlay?.updateAgenda(message.agenda);
          break;

        case "CAPTURE_STATE":
          overlay?.setCaptureState(message.captureState);
          if (message.captureState === CaptureState.Capturing) {
            startRecognition();
          } else if (
            message.captureState === CaptureState.Stopped ||
            message.captureState === CaptureState.Idle
          ) {
            stopRecognition();
          }
          break;

        case "MEETING_SUMMARY":
          stopRecognition();
          overlay?.setCaptureState(CaptureState.Stopped);
          overlay?.showSummary(message);
          break;
      }
      sendResponse({ ok: true });
      return true;
    },
  );

  sendToBackground({ type: "CONTENT_READY" });
  console.log("[Meeting Assistant] Overlay initialized for meeting");
}

function destroyOverlay() {
  stopRecognition();

  if (captionObserver) {
    captionObserver.stop();
    captionObserver = null;
  }

  overlay?.destroy();
  overlay = null;

  theme?.destroy();
  theme = null;

  host?.destroy();
  host = null;

  console.log("[Meeting Assistant] Overlay destroyed");
}

function init() {
  const meetingCode = getMeetingCode();

  if (!meetingCode) {
    console.log("[Meeting Assistant] Not a meeting page, overlay will not load");
    return;
  }

  console.log("[Meeting Assistant] Meeting page detected, code:", meetingCode);

  disconnectObserver = observeCallState((active) => {
    if (active) {
      console.log("[Meeting Assistant] Call is active, showing overlay");
      initOverlay();
    } else {
      console.log("[Meeting Assistant] Call is not active, hiding overlay");
      destroyOverlay();
    }
  });
}

window.addEventListener("beforeunload", () => {
  disconnectObserver?.();
  destroyOverlay();
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
