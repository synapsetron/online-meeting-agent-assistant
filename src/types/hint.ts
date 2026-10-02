export enum HintType {
  AgendaSuggestion = "agenda_suggestion",
  TopicDrift = "topic_drift",
  TimeWarning = "time_warning",
  MissedItem = "missed_item",
  Summary = "summary",
}

export interface Hint {
  id: string;
  type: HintType;
  agendaItemId: string;
  message: string;
  evidenceSegmentIds: string[];
  confidence: number;
  uncertainty?: string;
  timestamp: number;
  dismissed: boolean;
}
