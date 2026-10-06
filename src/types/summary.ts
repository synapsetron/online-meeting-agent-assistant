export interface SpeakerStats {
  speakerId: string;
  segments: number;
  words: number;
  /** Fraction of all transcribed words, 0..1. */
  share: number;
}

export interface AgendaItemStats {
  /** null = speech while no agenda item was active. */
  itemId: string | null;
  title: string;
  status: string;
  elapsedSeconds: number;
  estimatedMinutes?: number | null;
  segments: number;
  words: number;
  share: number;
}

export interface MeetingStats {
  durationSeconds: number;
  finalSegments: number;
  totalWords: number;
  speakers: SpeakerStats[];
  agenda: AgendaItemStats[];
  hintsShown: number;
}

export interface ActionItem {
  task: string;
  owner?: string | null;
}

export interface MeetingReport {
  source: "llm" | "fallback";
  summary: string;
  keyPoints: string[];
  decisions: string[];
  actionItems: ActionItem[];
  openQuestions: string[];
  truncated: boolean;
  /** Reason code when source is "fallback". */
  note?: string | null;
}

export interface MeetingSummaryPayload {
  summary: string;
  coveredItems: string[];
  missedItems: string[];
  stats?: MeetingStats | null;
  report?: MeetingReport | null;
  /** True while the AI report is still being generated. */
  pending?: boolean;
}
