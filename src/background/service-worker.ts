import type {
  PopupToBackground,
  ContentToBackground,
  BackgroundToPopup,
  BackgroundToContent,
  ClientToServer,
  ServerToClient,
  OffscreenToServiceWorker,
} from "@/types/messages";
import { MeetingStatus, CaptureState } from "@/types/meeting";
import { AgendaItemStatus } from "@/types/agenda";
import { WebSocketClient, type ConnectionState } from "@/shared/websocket-client";
import { DEFAULT_WS_URL } from "@/shared/constants";

import { createSessionState, pushTranscript, pushHint } from "./session-state";
import { startTabCapture, stopTabCapture } from "./tab-capture";

// ---- Session state ----

const state = createSessionState();

// ---- Persist / restore agenda ----

async function loadSavedAgenda(): Promise<void> {
  try {
    const result = await chrome.storage.local.get("agendaItems");
    if (Array.isArray(result.agendaItems) && result.agendaItems.length > 0) {
      state.agenda.items = result.agendaItems.map((item: { id: string; title: string; description?: string; estimatedMinutes?: number }, i: number) => ({
        id: item.id,
        title: item.title,
        description: item.description,
        status: AgendaItemStatus.Pending,
        estimatedMinutes: item.estimatedMinutes,
        elapsedSeconds: 0,
        evidence: [],
        order: i + 1,
      }));
    }
  } catch {
    // storage unavailable — keep empty agenda
  }
}

loadSavedAgenda();

// ---- Configurable settings ----

async function getBackendUrl(): Promise<string> {
  try {
    const result = await chrome.storage.local.get("backendUrl");
    return (result.backendUrl as string) || DEFAULT_WS_URL;
  } catch {
    return DEFAULT_WS_URL;
  }
}

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
        chrome.tabs.sendMessage(tab.id, message).catch(() => {});
      }
    }
  });
}

// ---- Handle incoming WebSocket messages ----

function handleServerMessage(data: unknown): void {
  const message = data as ServerToClient;

  switch (message.type) {
    case "SESSION_ACK":
      state.sessionId = message.sessionId;
      state.meeting.status = MeetingStatus.Connected;
      console.log("[ServiceWorker] Session established:", message.sessionId);
      break;

    case "NEW_TRANSCRIPT":
      if (message.segment.isFinal) {
        pushTranscript(state, message.segment);
      }
      broadcastToContentScripts({
        type: "NEW_TRANSCRIPT",
        segment: message.segment,
      });
      break;

    case "NEW_HINT":
      pushHint(state, message.hint);
      broadcastToContentScripts({
        type: "NEW_HINT",
        hint: message.hint,
      });
      break;

    case "AGENDA_UPDATE":
      state.agenda = message.agenda;
      broadcastToContentScripts({
        type: "AGENDA_UPDATE",
        agenda: message.agenda,
      });
      break;

    case "STATE_UPDATE":
      state.meeting = {
        ...state.meeting,
        ...message.meeting,
        // Preserve locally-managed fields that the backend doesn't track
        startTime: state.meeting.startTime,
        captureState: state.meeting.captureState,
        status: state.meeting.status,
      };
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

    case "CAPTURE_STATE":
      state.meeting.captureState = message.captureState;
      broadcastToContentScripts({
        type: "CAPTURE_STATE",
        captureState: message.captureState,
      });
      break;

    case "MEETING_SUMMARY":
      state.meeting.status = MeetingStatus.Ended;
      state.meeting.captureState = CaptureState.Stopped;
      broadcastToContentScripts({
        type: "MEETING_SUMMARY",
        summary: message.summary,
        coveredItems: message.coveredItems,
        missedItems: message.missedItems,
      });
      break;

    case "ERROR":
      console.error("[ServiceWorker] Server error:", message.message);
      break;

    default:
      console.warn("[ServiceWorker] Unknown message type:", (message as { type: string }).type);
  }
}

// ---- Start/stop WebSocket connection ----

async function getApiKey(): Promise<string> {
  try {
    const result = await chrome.storage.local.get("anthropicApiKey");
    return (result.anthropicApiKey as string) || "";
  } catch {
    return "";
  }
}

async function startConnection(): Promise<void> {
  const url = await getBackendUrl();
  const apiKey = await getApiKey();
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
    ...(apiKey ? { api_key: apiKey } : {}),
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
          stopTabCapture(state).catch((err) =>
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
              { id: "item-1", title: "General discussion", status: AgendaItemStatus.Pending, estimatedMinutes: 30, elapsedSeconds: 0, evidence: [], order: 1 },
            ];
          }
          startConnection().catch((err) => {
            console.error("[ServiceWorker] Failed to start connection:", err);
          });
          startTabCapture(state).catch((err) =>
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
          pushTranscript(state, message.segment);
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

      case "UPDATE_AGENDA": {
        state.agenda.items = message.items.map((item, i) => ({
          id: item.id,
          title: item.title,
          description: item.description,
          status: AgendaItemStatus.Pending,
          estimatedMinutes: item.estimatedMinutes,
          elapsedSeconds: 0,
          evidence: [],
          order: i + 1,
        }));
        chrome.storage.local.set({ agendaItems: message.items });
        sendResponse({ ok: true });
        break;
      }

      case "UPDATE_SETTINGS":
        chrome.storage.local.set({ settings: message.settings });
        sendResponse({ ok: true });
        break;

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
