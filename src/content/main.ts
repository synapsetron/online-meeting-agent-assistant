import { ShadowHost } from "./shadow-host";
import { OverlayContainer } from "./components/OverlayContainer";
import { ThemeManager } from "./components/ThemeManager";
import { SpeechRecognitionService } from "@/shared/speech-recognition";
import { MeetCaptionObserver } from "@/shared/meet-captions";
import { CaptureState } from "@/types/meeting";
import type { BackgroundToContent, ContentToBackground, PopupToBackground } from "@/types/messages";
import { resolveLocalUserName } from "@/shared/meet-user";
import { getMeetingCode, observeCallState } from "@/shared/meet-detector";
import { DEFAULT_SPEECH_LANGUAGE } from "@/shared/constants";

let disconnectObserver: (() => void) | null = null;
let host: ShadowHost | null = null;
let overlay: OverlayContainer | null = null;
let theme: ThemeManager | null = null;
let speechService: SpeechRecognitionService | null = null;
let captionObserver: MeetCaptionObserver | null = null;

function sendToBackground(msg: ContentToBackground | PopupToBackground): void {
  try {
    chrome.runtime.sendMessage(msg).catch(() => {});
  } catch {
    // Extension context invalidated after update — ignore
  }
}

function startRecognition(language?: string) {
  if (speechService) {
    speechService.stop();
  }

  const lang = language ?? DEFAULT_SPEECH_LANGUAGE;
  speechService = new SpeechRecognitionService(lang);

  // Remote participants come from Meet captions, independent of Web Speech support.
  startCaptionObserver();

  chrome.runtime.sendMessage({ type: "GET_STATE" } as PopupToBackground).then((response) => {
    if (response?.meeting?.id) {
      speechService?.setMeetingId(response.meeting.id);
      captionObserver?.setMeetingId(response.meeting.id);
    }
  }).catch(() => {});

  applyLocalUserName();

  if (!speechService.isSupported()) {
    console.warn("[Meeting Assistant] Web Speech API not supported in this browser");
    return;
  }

  speechService.onTranscript((segment) => {
    console.log("[Meeting Assistant] Transcript segment:", segment.text.substring(0, 50), "overlay:", !!overlay);
    overlay?.addTranscript(segment);
    sendToBackground({ type: "TRANSCRIPT_SEGMENT", segment });
  });

  speechService.start();
  console.log("[Meeting Assistant] Speech recognition started, language:", lang);
}

/** Meet may render the account name late, so retry for a short while. */
function applyLocalUserName(attempt = 0) {
  resolveLocalUserName().then((name) => {
    if (name) {
      speechService?.setSpeakerId(name);
      captionObserver?.setLocalUserName(name);
      console.log("[Meeting Assistant] Local user name:", name);
    } else if (attempt < 10 && speechService) {
      setTimeout(() => applyLocalUserName(attempt + 1), 3000);
    }
  });
}

function startCaptionObserver() {
  if (captionObserver) {
    captionObserver.stop();
  }

  captionObserver = new MeetCaptionObserver();
  captionObserver.setSkipLocalUser(true);

  captionObserver.onCaption((segment) => {
    console.log("[Meeting Assistant] Caption from", segment.speakerId + ":", segment.text.substring(0, 50));
    overlay?.addTranscript(segment);
    sendToBackground({ type: "TRANSCRIPT_SEGMENT", segment });
  });

  captionObserver.start();
  captionObserver.tryEnableCaptions();

  console.log("[Meeting Assistant] Caption observer started for remote participants");
}

function stopRecognition() {
  if (speechService) {
    speechService.stop();
    speechService = null;
    console.log("[Meeting Assistant] Speech recognition stopped");
  }

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
          overlay?.setCaptureState(message.meeting.captureState);
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
            loadLanguageSetting().then((lang) => {
              startRecognition(lang);
            });
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

async function loadLanguageSetting(): Promise<string> {
  try {
    const result = await chrome.storage.local.get("speechLanguage");
    return (result.speechLanguage as string) || DEFAULT_SPEECH_LANGUAGE;
  } catch {
    return DEFAULT_SPEECH_LANGUAGE;
  }
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
