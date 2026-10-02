import type {
  PopupToBackground,
  ContentToBackground,
  BackgroundToPopup,
  BackgroundToContent,
  ClientToServer,
  ServerToClient,
  OffscreenToServiceWorker,
} from "@/types/messages";
import { MeetingStatus, CaptureState, type MeetingInfo } from "@/types/meeting";
import { AgendaItemStatus, type AgendaState, type AgendaItem } from "@/types/agenda";
import type { Hint } from "@/types/hint";
import type { TranscriptSegment } from "@/types/transcript";
import { WebSocketClient, type ConnectionState } from "@/shared/websocket-client";

// ---- Configurable settings ----

const DEFAULT_WS_URL = "ws://localhost:8000/ws";

async function getBackendUrl(): Promise<string> {
  try {
    const result = await chrome.storage.local.get("backendUrl");
    return (result.backendUrl as string) || DEFAULT_WS_URL;
  } catch {
    return DEFAULT_WS_URL;
  }
}

// ---- Session state ----

const OFFSCREEN_URL = "src/offscreen/offscreen.html";

const state = {
  meeting: {
    id: "",
    title: "",
    startTime: 0,
    participants: [],
    status: MeetingStatus.Disconnected,
    captureState: CaptureState.Idle,
  } as MeetingInfo,

  agenda: {
    items: [] as AgendaItem[],
    activeItemId: null,
    startTime: 0,
    totalElapsedSeconds: 0,
  } as AgendaState,

  hints: [] as Hint[],
  recentTranscript: [] as TranscriptSegment[],
  sessionId: null as string | null,
  tabCaptureActive: false,
};

// ---- WebSocket client ----

let wsClient: WebSocketClient | null = null;

function getWsClient(): WebSocketClient {
  if (!wsClient) {
    wsClient = new WebSocketClient();
  }
  return wsClient;
}

// ---- Broadcast to content scripts ----

function broadcastToContentScripts(message: BackgroundToContent): void {
  chrome.tabs.query({}, (tabs) => {
    for (const tab of tabs) {
      if (tab.id !== undefined) {
        chrome.tabs.sendMessage(tab.id, message).catch(() => {
          // Tab may not have content script loaded — ignore
        });
      }
    }
  });
}

// ---- Handle incoming WebSocket messages ----

function handleServerMessage(data: unknown): void {
  const message = data as ServerToClient;

  switch (message.type) {
    case "SESSION_ACK": {
      state.sessionId = message.session_id;
      state.meeting.status = MeetingStatus.Connected;
      console.log("[ServiceWorker] Session established:", message.session_id);
      break;
    }

    case "NEW_TRANSCRIPT": {
      const MAX_RECENT = 100;
      if (message.segment.isFinal) {
        state.recentTranscript.push(message.segment);
        if (state.recentTranscript.length > MAX_RECENT) {
          state.recentTranscript = state.recentTranscript.slice(-MAX_RECENT);
        }
      }
      broadcastToContentScripts({
        type: "NEW_TRANSCRIPT",
        segment: message.segment,
      });
      break;
    }

    case "NEW_HINT": {
      state.hints.push(message.hint);
      const MAX_HINTS = 50;
      if (state.hints.length > MAX_HINTS) {
        state.hints = state.hints.slice(-MAX_HINTS);
      }
      broadcastToContentScripts({
        type: "NEW_HINT",
        hint: message.hint,
      });
      break;
    }

    case "AGENDA_UPDATE": {
      state.agenda = message.agenda;
      broadcastToContentScripts({
        type: "AGENDA_UPDATE",
        agenda: message.agenda,
      });
      break;
    }

    case "STATE_UPDATE": {
      state.meeting = { ...state.meeting, ...message.meeting };
      state.agenda = message.agenda;
      if (message.hints) state.hints = message.hints;
      if (message.recentTranscript) state.recentTranscript = message.recentTranscript;
      broadcastToContentScripts({
        type: "STATE_UPDATE",
        meeting: state.meeting,
        agenda: state.agenda,
        hints: message.hints,
        recentTranscript: message.recentTranscript,
      });
      break;
    }

    case "CAPTURE_STATE": {
      state.meeting.captureState = message.captureState;
      broadcastToContentScripts({
        type: "CAPTURE_STATE",
        captureState: message.captureState,
      });
      break;
    }

    case "MEETING_SUMMARY": {
      state.meeting.status = MeetingStatus.Ended;
      state.meeting.captureState = CaptureState.Stopped;
      broadcastToContentScripts({
        type: "MEETING_SUMMARY",
        summary: message.summary,
        coveredItems: message.covered_items,
        missedItems: message.missed_items,
      });
      break;
    }

    case "ERROR": {
      console.error("[ServiceWorker] Server error:", message.message);
      break;
    }

    default:
      console.warn("[ServiceWorker] Unknown message type:", (message as { type: string }).type);
  }
}

// ---- Start/stop WebSocket connection ----

async function startConnection(): Promise<void> {
  const url = await getBackendUrl();
  const client = getWsClient();
  client.setUrl(url);

  client.onStateChange((connectionState: ConnectionState) => {
    switch (connectionState) {
      case "connecting":
      case "reconnecting":
        state.meeting.status = MeetingStatus.Connecting;
        break;
      case "connected":
        break;
      case "disconnected":
        if (state.meeting.captureState === CaptureState.Capturing) {
          state.meeting.status = MeetingStatus.Disconnected;
        }
        break;
    }
  });

  client.onMessage(handleServerMessage);

  const connectMsg: ClientToServer = {
    type: "CONNECT",
    meeting_id: state.meeting.id || `meeting-${Date.now()}`,
    title: state.meeting.title || "Untitled Meeting",
    agenda_items: state.agenda.items.map((item) => ({
      id: item.id,
      title: item.title,
      description: item.description,
      estimated_minutes: item.estimatedMinutes,
    })),
    participants: state.meeting.participants,
  };

  state.meeting.status = MeetingStatus.Connecting;
  state.meeting.captureState = CaptureState.Capturing;
  state.meeting.startTime = Date.now();

  client.connect(connectMsg);
}

function stopConnection(): void {
  if (wsClient) {
    wsClient.send({ type: "AUDIO_STOP" } as ClientToServer);
    wsClient.disconnect();
  }
  state.meeting.captureState = CaptureState.Stopped;
  state.meeting.status = MeetingStatus.Disconnected;
  state.sessionId = null;
}

// ---------------------------------------------------------------------------
// Offscreen document management
// ---------------------------------------------------------------------------

async function hasOffscreenDocument(): Promise<boolean> {
  if (chrome.offscreen && typeof chrome.offscreen.hasDocument === "function") {
    return chrome.offscreen.hasDocument();
  }

  if (chrome.runtime.getContexts) {
    const contexts = await chrome.runtime.getContexts({
      contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT],
      documentUrls: [chrome.runtime.getURL(OFFSCREEN_URL)],
    });
    return contexts.length > 0;
  }

  return false;
}

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

async function closeOffscreenDocument(): Promise<void> {
  if (await hasOffscreenDocument()) {
    await chrome.offscreen.closeDocument();
  }
}

// ---------------------------------------------------------------------------
// Tab capture management
// ---------------------------------------------------------------------------

async function startTabCapture(): Promise<boolean> {
  try {
    await ensureOffscreenDocument();
    const streamId = await chrome.tabCapture.getMediaStreamId({});

    await chrome.runtime.sendMessage({
      type: "START_TAB_CAPTURE",
      streamId,
    });

    state.tabCaptureActive = true;
    console.log("[ServiceWorker] Tab capture initiated");
    return true;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown tab capture error";
    console.warn("[ServiceWorker] Tab capture failed, microphone-only mode:", message);
    await closeOffscreenDocument().catch(() => {});
    state.tabCaptureActive = false;
    return false;
  }
}

async function stopTabCapture(): Promise<void> {
  if (!state.tabCaptureActive) {
    return;
  }

  try {
    await chrome.runtime.sendMessage({ type: "STOP_TAB_CAPTURE" });
  } catch {
    // Offscreen document may already be closed
  }

  await closeOffscreenDocument().catch(() => {});
  state.tabCaptureActive = false;
  console.log("[ServiceWorker] Tab capture stopped");
}

// ---- Message listener ----

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
          stopConnection();
          stopTabCapture().catch((err) =>
            console.warn("[ServiceWorker] Error stopping tab capture:", err),
          );
          broadcastToContentScripts({
            type: "CAPTURE_STATE",
            captureState: CaptureState.Stopped,
          });
        } else {
          if (!state.meeting.id) {
            state.meeting.id = `meeting-${Date.now()}`;
          }
          if (!state.meeting.title) {
            state.meeting.title = "Meeting";
          }
          if (state.agenda.items.length === 0) {
            state.agenda.items = [
              { id: "1", title: "General discussion", status: AgendaItemStatus.Pending, estimatedMinutes: 30, elapsedSeconds: 0, evidence: [], order: 1 },
            ];
          }
          startConnection().catch((err) => {
            console.error("[ServiceWorker] Failed to start connection:", err);
          });
          startTabCapture().catch((err) =>
            console.warn("[ServiceWorker] Error starting tab capture:", err),
          );
          broadcastToContentScripts({
            type: "CAPTURE_STATE",
            captureState: CaptureState.Capturing,
          });
        }
        sendResponse({ captureState: state.meeting.captureState });
        break;
      }

      case "DISMISS_HINT": {
        const hint = state.hints.find((h) => h.id === message.hintId);
        if (hint) hint.dismissed = true;
        if (wsClient) {
          wsClient.send({ type: "DISMISS_HINT", hint_id: message.hintId } as ClientToServer);
        }
        sendResponse({ ok: true });
        break;
      }

      case "TRANSCRIPT_SEGMENT": {
        if (wsClient) {
          wsClient.send({ type: "TRANSCRIPT", segment: message.segment } as ClientToServer);
        }
        if (message.segment.isFinal) {
          state.recentTranscript.push(message.segment);
          const MAX_RECENT = 100;
          if (state.recentTranscript.length > MAX_RECENT) {
            state.recentTranscript = state.recentTranscript.slice(-MAX_RECENT);
          }
        }
        sendResponse({ ok: true });
        break;
      }

      case "CONTENT_READY":
        broadcastToContentScripts({
          type: "STATE_UPDATE",
          meeting: state.meeting,
          agenda: state.agenda,
          hints: state.hints,
          recentTranscript: state.recentTranscript,
        });
        sendResponse({ ok: true });
        break;

      case "UPDATE_SETTINGS":
        chrome.storage.local.set({ settings: message.settings });
        sendResponse({ ok: true });
        break;

      // Messages from the offscreen document
      case "TAB_CAPTURE_STARTED":
        console.log("[ServiceWorker] Offscreen confirmed tab capture started");
        sendResponse({ ok: true });
        break;
      case "TAB_CAPTURE_STOPPED":
        state.tabCaptureActive = false;
        console.log("[ServiceWorker] Offscreen confirmed tab capture stopped");
        sendResponse({ ok: true });
        break;
      case "TAB_CAPTURE_ERROR":
        state.tabCaptureActive = false;
        console.warn("[ServiceWorker] Tab capture error:", message.error);
        sendResponse({ ok: true });
        break;

      default:
        sendResponse({ ok: true });
    }
    return true;
  },
);

chrome.runtime.onInstalled.addListener(() => {
  console.log("[Meeting Assistant] Extension installed");
});
