import type { AgendaState } from "./agenda";
import type { TranscriptSegment } from "./transcript";
import type { Hint } from "./hint";
import type { MeetingInfo, CaptureState } from "./meeting";

export type PopupToBackground =
  | { type: "GET_STATE" }
  | { type: "TOGGLE_CAPTURE" }
  | { type: "UPDATE_SETTINGS"; settings: Record<string, unknown> };

export type BackgroundToContent =
  | { type: "STATE_UPDATE"; meeting: MeetingInfo; agenda: AgendaState }
  | { type: "NEW_TRANSCRIPT"; segment: TranscriptSegment }
  | { type: "NEW_HINT"; hint: Hint }
  | { type: "AGENDA_UPDATE"; agenda: AgendaState }
  | { type: "CAPTURE_STATE"; captureState: CaptureState };

export type ContentToBackground =
  | { type: "DISMISS_HINT"; hintId: string }
  | { type: "CONTENT_READY" };

export type BackgroundToPopup = {
  type: "FULL_STATE";
  meeting: MeetingInfo;
  agenda: AgendaState;
  hints: Hint[];
  recentTranscript: TranscriptSegment[];
};

export type ServiceWorkerToOffscreen =
  | { type: "START_TAB_CAPTURE"; streamId: string }
  | { type: "STOP_TAB_CAPTURE" };

export type OffscreenToServiceWorker =
  | { type: "TAB_CAPTURE_STARTED" }
  | { type: "TAB_CAPTURE_STOPPED" }
  | { type: "TAB_CAPTURE_ERROR"; error: string };
