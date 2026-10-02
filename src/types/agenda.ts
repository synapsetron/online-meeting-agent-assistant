export enum AgendaItemStatus {
  Pending = "pending",
  Active = "active",
  Covered = "covered",
  Deferred = "deferred",
  Skipped = "skipped",
}

export interface AgendaItem {
  id: string;
  title: string;
  description?: string;
  status: AgendaItemStatus;
  estimatedMinutes?: number;
  elapsedSeconds: number;
  evidence: string[];
  order: number;
}

export interface AgendaState {
  items: AgendaItem[];
  activeItemId: string | null;
  startTime: number;
  totalElapsedSeconds: number;
}
