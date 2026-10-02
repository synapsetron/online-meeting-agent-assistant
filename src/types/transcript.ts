export interface Speaker {
  id: string;
  name: string;
  color: string;
}

export interface TranscriptSegment {
  id: string;
  meetingId: string;
  speakerId: string;
  text: string;
  timestamp: number;
  isFinal: boolean;
  confidence?: number;
  version: number;
}
