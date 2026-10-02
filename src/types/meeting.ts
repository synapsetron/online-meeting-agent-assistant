export enum MeetingStatus {
  Disconnected = "disconnected",
  Connecting = "connecting",
  Connected = "connected",
  Ended = "ended",
}

export enum CaptureState {
  Idle = "idle",
  Capturing = "capturing",
  Paused = "paused",
  Stopped = "stopped",
}

export interface MeetingInfo {
  id: string;
  title: string;
  startTime: number;
  participants: string[];
  status: MeetingStatus;
  captureState: CaptureState;
}
