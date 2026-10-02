import type { PopupToBackground, ContentToBackground, BackgroundToPopup } from "@/types/messages";
import { MeetingStatus, CaptureState, type MeetingInfo } from "@/types/meeting";
import { AgendaItemStatus, type AgendaState } from "@/types/agenda";
import type { Hint } from "@/types/hint";
import type { TranscriptSegment } from "@/types/transcript";

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
};

chrome.runtime.onMessage.addListener(
  (
    message: PopupToBackground | ContentToBackground,
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
        } else {
          state.meeting.captureState = CaptureState.Capturing;
          state.meeting.startTime = Date.now();
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
    }
    return true;
  },
);

chrome.runtime.onInstalled.addListener(() => {
  console.log("[Meeting Assistant] Extension installed");
});
