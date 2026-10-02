import type {
  PopupToBackground,
  ContentToBackground,
  BackgroundToPopup,
  OffscreenToServiceWorker,
} from "@/types/messages";
import { MeetingStatus, CaptureState, type MeetingInfo } from "@/types/meeting";
import { AgendaItemStatus, type AgendaState } from "@/types/agenda";
import type { Hint } from "@/types/hint";
import type { TranscriptSegment } from "@/types/transcript";

const OFFSCREEN_URL = "src/offscreen/offscreen.html";

const state = {
  meeting: {
    id: "meeting-001",
    title: "Thesis progress meeting",
    startTime: Date.now(),
    participants: ["Olena K.", "Dmytro S.", "Prof. Ivanov"],
    status: MeetingStatus.Connected,
    captureState: CaptureState.Idle,
  } as MeetingInfo,

  agenda: {
    items: [
      { id: "1", title: "Project overview", status: AgendaItemStatus.Pending, estimatedMinutes: 5, elapsedSeconds: 0, evidence: [], order: 1 },
      { id: "2", title: "Architecture review", status: AgendaItemStatus.Pending, estimatedMinutes: 10, elapsedSeconds: 0, evidence: [], order: 2 },
      { id: "3", title: "ASR integration", status: AgendaItemStatus.Pending, estimatedMinutes: 8, elapsedSeconds: 0, evidence: [], order: 3 },
      { id: "4", title: "Evaluation protocol", status: AgendaItemStatus.Pending, estimatedMinutes: 10, elapsedSeconds: 0, evidence: [], order: 4 },
      { id: "5", title: "Timeline & milestones", status: AgendaItemStatus.Pending, estimatedMinutes: 5, elapsedSeconds: 0, evidence: [], order: 5 },
      { id: "6", title: "Open questions", status: AgendaItemStatus.Pending, estimatedMinutes: 7, elapsedSeconds: 0, evidence: [], order: 6 },
    ],
    activeItemId: null,
    startTime: Date.now(),
    totalElapsedSeconds: 0,
  } satisfies AgendaState,

  hints: [] as Hint[],
  recentTranscript: [] as TranscriptSegment[],
  tabCaptureActive: false,
};

// ---------------------------------------------------------------------------
// Offscreen document management
// ---------------------------------------------------------------------------

/**
 * Check whether an offscreen document already exists.
 */
async function hasOffscreenDocument(): Promise<boolean> {
  // chrome.offscreen.hasDocument is available since Chrome 150;
  // fall back to checking via getContexts for older versions.
  if (chrome.offscreen && typeof chrome.offscreen.hasDocument === "function") {
    return chrome.offscreen.hasDocument();
  }

  // Fallback: use runtime.getContexts (Chrome 116+)
  if (chrome.runtime.getContexts) {
    const contexts = await chrome.runtime.getContexts({
      contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT],
      documentUrls: [chrome.runtime.getURL(OFFSCREEN_URL)],
    });
    return contexts.length > 0;
  }

  return false;
}

/**
 * Ensure an offscreen document is created for audio processing.
 */
async function ensureOffscreenDocument(): Promise<void> {
  if (await hasOffscreenDocument()) {
    return;
  }

  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: [chrome.offscreen.Reason.USER_MEDIA],
    justification: "Processing tab audio capture for meeting transcription",
  });
}

/**
 * Close the offscreen document if it exists.
 */
async function closeOffscreenDocument(): Promise<void> {
  if (await hasOffscreenDocument()) {
    await chrome.offscreen.closeDocument();
  }
}

// ---------------------------------------------------------------------------
// Tab capture management
// ---------------------------------------------------------------------------

/**
 * Start capturing audio from the active tab.
 *
 * 1. Creates an offscreen document (if not already present)
 * 2. Gets a media stream ID from tabCapture
 * 3. Sends the stream ID to the offscreen document for processing
 *
 * If tabCapture fails, logs the error and returns false so the caller
 * can fall back to microphone-only mode (Web Speech API).
 */
async function startTabCapture(): Promise<boolean> {
  try {
    // Step 1: Ensure offscreen document exists
    await ensureOffscreenDocument();

    // Step 2: Get media stream ID for the active tab
    const streamId = await chrome.tabCapture.getMediaStreamId({});

    // Step 3: Send stream ID to offscreen document
    await chrome.runtime.sendMessage({
      type: "START_TAB_CAPTURE",
      streamId,
    });

    state.tabCaptureActive = true;
    console.log("[Service Worker] Tab capture initiated, stream ID sent to offscreen document");
    return true;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown tab capture error";
    console.warn(
      "[Service Worker] Tab capture failed, falling back to microphone-only mode:",
      message,
    );
    // Clean up offscreen document if capture failed
    await closeOffscreenDocument().catch(() => {});
    state.tabCaptureActive = false;
    return false;
  }
}

/**
 * Stop tab audio capture and clean up resources.
 */
async function stopTabCapture(): Promise<void> {
  if (!state.tabCaptureActive) {
    return;
  }

  try {
    // Tell offscreen document to stop capture
    await chrome.runtime.sendMessage({ type: "STOP_TAB_CAPTURE" });
  } catch {
    // Offscreen document may already be closed
  }

  // Close the offscreen document
  await closeOffscreenDocument().catch(() => {});
  state.tabCaptureActive = false;
  console.log("[Service Worker] Tab capture stopped");
}

// ---------------------------------------------------------------------------
// Message handling
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener(
  (
    message: PopupToBackground | ContentToBackground | OffscreenToServiceWorker,
    _sender,
    sendResponse,
  ) => {
    switch (message.type) {
      case "GET_STATE": {
        const response: BackgroundToPopup = {
          type: "FULL_STATE",
          meeting: state.meeting,
          agenda: state.agenda,
          hints: state.hints,
          recentTranscript: state.recentTranscript,
        };
        sendResponse(response);
        break;
      }
      case "TOGGLE_CAPTURE": {
        if (state.meeting.captureState === CaptureState.Capturing) {
          state.meeting.captureState = CaptureState.Stopped;
          // Stop tab capture asynchronously
          stopTabCapture().catch((err) =>
            console.warn("[Service Worker] Error stopping tab capture:", err),
          );
        } else {
          state.meeting.captureState = CaptureState.Capturing;
          state.meeting.startTime = Date.now();
          // Attempt tab capture; microphone-only (Web Speech API) continues
          // regardless of whether this succeeds.
          startTabCapture().catch((err) =>
            console.warn("[Service Worker] Error starting tab capture:", err),
          );
        }
        sendResponse({ captureState: state.meeting.captureState });
        break;
      }
      case "DISMISS_HINT": {
        const hint = state.hints.find((h) => h.id === message.hintId);
        if (hint) hint.dismissed = true;
        sendResponse({ ok: true });
        break;
      }
      case "CONTENT_READY":
        sendResponse({ ok: true });
        break;
      case "UPDATE_SETTINGS":
        chrome.storage.local.set({ settings: message.settings });
        sendResponse({ ok: true });
        break;

      // Messages from the offscreen document
      case "TAB_CAPTURE_STARTED":
        console.log("[Service Worker] Offscreen document confirmed tab capture started");
        sendResponse({ ok: true });
        break;
      case "TAB_CAPTURE_STOPPED":
        state.tabCaptureActive = false;
        console.log("[Service Worker] Offscreen document confirmed tab capture stopped");
        sendResponse({ ok: true });
        break;
      case "TAB_CAPTURE_ERROR":
        state.tabCaptureActive = false;
        console.warn("[Service Worker] Tab capture error from offscreen:", message.error);
        sendResponse({ ok: true });
        break;
    }
    return true;
  },
);

chrome.runtime.onInstalled.addListener(() => {
  console.log("[Meeting Assistant] Extension installed");
});
