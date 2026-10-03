import { MeetingStatus, CaptureState, type MeetingInfo } from "@/types/meeting";
import type { AgendaState, AgendaItem } from "@/types/agenda";
import type { Hint } from "@/types/hint";
import type { TranscriptSegment } from "@/types/transcript";

const MAX_RECENT_TRANSCRIPTS = 100;
const MAX_HINTS = 50;

export interface SessionState {
  meeting: MeetingInfo;
  agenda: AgendaState;
  hints: Hint[];
  recentTranscript: TranscriptSegment[];
  sessionId: string | null;
  tabCaptureActive: boolean;
}

export function createSessionState(): SessionState {
  return {
    meeting: {
      id: "",
      title: "",
      startTime: 0,
      participants: [],
      status: MeetingStatus.Disconnected,
      captureState: CaptureState.Idle,
    },
    agenda: {
      items: [] as AgendaItem[],
      activeItemId: null,
      startTime: 0,
      totalElapsedSeconds: 0,
    },
    hints: [],
    recentTranscript: [],
    sessionId: null,
    tabCaptureActive: false,
  };
}

export function pushTranscript(state: SessionState, segment: TranscriptSegment): void {
  state.recentTranscript.push(segment);
  if (state.recentTranscript.length > MAX_RECENT_TRANSCRIPTS) {
    state.recentTranscript = state.recentTranscript.slice(-MAX_RECENT_TRANSCRIPTS);
  }
}

export function pushHint(state: SessionState, hint: Hint): void {
  state.hints.push(hint);
  if (state.hints.length > MAX_HINTS) {
    state.hints = state.hints.slice(-MAX_HINTS);
  }
}
