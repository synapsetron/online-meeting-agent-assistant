import { useState, useEffect, useCallback } from "react";
import { MeetingStatus, CaptureState, type MeetingInfo } from "@/types/meeting";
import type { AgendaItem } from "@/types/agenda";
import type { PopupToBackground, BackgroundToPopup } from "@/types/messages";

interface ChromeState {
  meetingStatus: MeetingStatus;
  captureState: CaptureState;
  meetingTitle: string;
  startTime: number;
  agendaItems: AgendaItem[];
}

export function useChromeState(pollIntervalMs = 2000): ChromeState & { refresh: () => void } {
  const [state, setState] = useState<ChromeState>({
    meetingStatus: MeetingStatus.Disconnected,
    captureState: CaptureState.Idle,
    meetingTitle: "",
    startTime: 0,
    agendaItems: [],
  });

  const fetchState = useCallback(() => {
    chrome.runtime.sendMessage(
      { type: "GET_STATE" } as PopupToBackground,
      (response: BackgroundToPopup) => {
        if (!response || response.type !== "FULL_STATE") return;
        setState({
          meetingStatus: response.meeting.status,
          captureState: response.meeting.captureState,
          meetingTitle: response.meeting.title || "",
          startTime: response.meeting.startTime || 0,
          agendaItems: response.agenda.items,
        });
      },
    );
  }, []);

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, pollIntervalMs);
    return () => clearInterval(interval);
  }, [fetchState, pollIntervalMs]);

  return { ...state, refresh: fetchState };
}
