import type { AgendaState } from "./agenda";
import type { TranscriptSegment } from "./transcript";
import type { Hint } from "./hint";
import type { MeetingInfo, CaptureState } from "./meeting";

export type PopupToBackground =
  | { type: "GET_STATE" }
  | { type: "TOGGLE_CAPTURE" }
  | { type: "UPDATE_AGENDA"; items: { id: string; title: string; description?: string; estimatedMinutes?: number }[] }
  | { type: "UPDATE_SETTINGS"; settings: Record<string, unknown> };

export type BackgroundToContent =
  | { type: "STATE_UPDATE"; meeting: MeetingInfo; agenda: AgendaState; hints?: Hint[]; recentTranscript?: TranscriptSegment[] }
  | { type: "NEW_TRANSCRIPT"; segment: TranscriptSegment }
  | { type: "NEW_HINT"; hint: Hint }
  | { type: "AGENDA_UPDATE"; agenda: AgendaState }
  | { type: "CAPTURE_STATE"; captureState: CaptureState }
  | { type: "MEETING_SUMMARY"; summary: string; coveredItems: string[]; missedItems: string[] };

export type ContentToBackground =
  | { type: "DISMISS_HINT"; hintId: string }
  | { type: "CONTENT_READY" }
  | { type: "TRANSCRIPT_SEGMENT"; segment: TranscriptSegment }
  | { type: "START_RECOGNITION"; language?: string }
  | { type: "STOP_RECOGNITION" };

export type BackgroundToPopup = {
  type: "FULL_STATE";
  meeting: MeetingInfo;
  agenda: AgendaState;
  hints: Hint[];
  recentTranscript: TranscriptSegment[];
};

export type ClientToServer =
  | { type: "CONNECT"; meeting_id: string; title: string; agenda_items: { id: string; title: string; description?: string; estimated_minutes?: number }[]; participants: string[]; api_key?: string }
  | { type: "TRANSCRIPT"; segment: TranscriptSegment }
  | { type: "AUDIO_START" }
  | { type: "AUDIO_STOP" }
  | { type: "DISMISS_HINT"; hint_id: string };

export type ServerToClient =
  | { type: "SESSION_ACK"; sessionId: string }
  | { type: "NEW_TRANSCRIPT"; segment: TranscriptSegment }
  | { type: "AGENDA_UPDATE"; agenda: AgendaState }
  | { type: "NEW_HINT"; hint: Hint }
  | { type: "STATE_UPDATE"; meeting: MeetingInfo; agenda: AgendaState; hints?: Hint[]; recentTranscript?: TranscriptSegment[] }
  | { type: "CAPTURE_STATE"; captureState: CaptureState }
  | { type: "MEETING_SUMMARY"; summary: string; coveredItems: string[]; missedItems: string[] }
  | { type: "ERROR"; message: string };

export type ServiceWorkerToOffscreen =
  | { type: "START_TAB_CAPTURE"; streamId: string }
  | { type: "STOP_TAB_CAPTURE" };

export type OffscreenToServiceWorker =
  | { type: "TAB_CAPTURE_STARTED" }
  | { type: "TAB_CAPTURE_STOPPED" }
  | { type: "TAB_CAPTURE_ERROR"; error: string };
