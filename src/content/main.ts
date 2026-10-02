import { ShadowHost } from "./shadow-host";
import { OverlayContainer } from "./components/OverlayContainer";
import { ThemeManager } from "./components/ThemeManager";
import { SpeechRecognitionService } from "@/shared/speech-recognition";
import { CaptureState } from "@/types/meeting";
import type { BackgroundToContent, ContentToBackground, PopupToBackground } from "@/types/messages";

const DEFAULT_LANGUAGE = "uk-UA";

function init() {
  const host = new ShadowHost("open");

  let speechService: SpeechRecognitionService | null = null;

  const overlay = new OverlayContainer({
    onDismissHint: (hintId) => {
      console.log("[Meeting Assistant] Hint dismissed:", hintId);
      const msg: ContentToBackground = { type: "DISMISS_HINT", hintId };
      chrome.runtime.sendMessage(msg).catch((err) => {
        console.error("[Meeting Assistant] Failed to send DISMISS_HINT:", err);
      });
    },
    onStopCapture: () => {
      stopRecognition();
      overlay.setCaptureState(CaptureState.Stopped);
      const msg: ContentToBackground = { type: "STOP_RECOGNITION" };
      chrome.runtime.sendMessage(msg).catch((err) => {
        console.error("[Meeting Assistant] Failed to send STOP_RECOGNITION:", err);
      });
    },
  });

  host.mount(overlay.root);

  const theme = new ThemeManager(host.host);
  theme.init();

  // ---- Speech recognition ----

  function startRecognition(language?: string) {
    if (speechService) {
      speechService.stop();
    }

    const lang = language ?? DEFAULT_LANGUAGE;
    speechService = new SpeechRecognitionService(lang);

    if (!speechService.isSupported()) {
      console.warn("[Meeting Assistant] Web Speech API not supported in this browser");
      return;
    }

    // Load meetingId from current state if available
    chrome.runtime.sendMessage({ type: "GET_STATE" } as PopupToBackground).then((response) => {
      if (response?.meeting?.id) {
        speechService?.setMeetingId(response.meeting.id);
      }
    }).catch(() => {
      // Ignore — service worker may not be ready
    });

    speechService.onTranscript((segment) => {
      // Show in overlay immediately
      overlay.addTranscript(segment);
      // Forward to service worker which sends to backend
      const msg: ContentToBackground = { type: "TRANSCRIPT_SEGMENT", segment };
      chrome.runtime.sendMessage(msg).catch((err) => {
        console.error("[Meeting Assistant] Failed to send transcript:", err);
      });
    });

    speechService.start();
    console.log("[Meeting Assistant] Speech recognition started, language:", lang);
  }

  function stopRecognition() {
    if (speechService) {
      speechService.stop();
      speechService = null;
      console.log("[Meeting Assistant] Speech recognition stopped");
    }
  }

  // ---- Listen for messages from service worker ----

  chrome.runtime.onMessage.addListener(
    (message: BackgroundToContent, _sender, sendResponse) => {
      switch (message.type) {
        case "STATE_UPDATE":
          overlay.updateAgenda(message.agenda);
          if (message.hints) {
            for (const hint of message.hints) {
              if (!hint.dismissed) {
                overlay.addHint(hint);
              }
            }
          }
          if (message.recentTranscript) {
            for (const segment of message.recentTranscript) {
              overlay.addTranscript(segment);
            }
          }
          break;

        case "NEW_TRANSCRIPT":
          overlay.addTranscript(message.segment);
          break;

        case "NEW_HINT":
          overlay.addHint(message.hint);
          break;

        case "AGENDA_UPDATE":
          overlay.updateAgenda(message.agenda);
          break;

        case "CAPTURE_STATE":
          overlay.setCaptureState(message.captureState);
          if (message.captureState === CaptureState.Capturing) {
            // Load language setting and start recognition
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
          console.log("[Meeting Assistant] Meeting summary received:", message.summary);
          stopRecognition();
          overlay.setCaptureState(CaptureState.Stopped);
          break;
      }
      sendResponse({ ok: true });
      return true;
    },
  );

  // ---- Notify service worker that content script is ready ----

  const readyMsg: ContentToBackground = { type: "CONTENT_READY" };
  chrome.runtime.sendMessage(readyMsg).catch(() => {
    // Service worker may not be ready yet — this is fine
  });

  // ---- Cleanup on unload ----

  window.addEventListener("beforeunload", () => {
    stopRecognition();
    overlay.destroy();
    theme.destroy();
    host.destroy();
  });
}

async function loadLanguageSetting(): Promise<string> {
  try {
    const result = await chrome.storage.local.get("speechLanguage");
    return (result.speechLanguage as string) || DEFAULT_LANGUAGE;
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
