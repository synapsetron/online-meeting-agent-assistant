import type { AgendaState, AgendaItem } from "@/types/agenda";
import { AgendaItemStatus } from "@/types/agenda";
import type { TranscriptSegment, Speaker } from "@/types/transcript";
import type { Hint } from "@/types/hint";
import { CaptureState } from "@/types/meeting";

export interface ScenarioEvent {
  timeMs: number;
  action:
    | { type: "transcript"; segment: TranscriptSegment }
    | { type: "transcript_partial"; segment: TranscriptSegment }
    | { type: "agenda_transition"; itemId: string; status: AgendaItemStatus }
    | { type: "hint"; hint: Hint };
}

export interface Scenario {
  speakers: Speaker[];
  agendaItems: AgendaItem[];
  events: ScenarioEvent[];
}

type EventMap = {
  speakers: Speaker[];
  agenda: AgendaState;
  transcript: TranscriptSegment;
  hint: Hint;
  captureState: CaptureState;
  done: void;
};

type Listener<K extends keyof EventMap> = (data: EventMap[K]) => void;

export class MeetingSimulator {
  private scenario: Scenario;
  private listeners = new Map<keyof EventMap, Set<Listener<never>>>();
  private timers: ReturnType<typeof setTimeout>[] = [];
  private startTime = 0;
  private speed = 1;
  private agendaState: AgendaState;
  private isRunning = false;
  private isPaused = false;
  private pausedAt = 0;
  private elapsedBeforePause = 0;

  constructor(scenario: Scenario) {
    this.scenario = scenario;
    this.agendaState = {
      items: structuredClone(scenario.agendaItems),
      activeItemId: null,
      startTime: 0,
      totalElapsedSeconds: 0,
    };
  }

  on<K extends keyof EventMap>(event: K, listener: Listener<K>) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    (this.listeners.get(event) as Set<Listener<K>>).add(listener);
  }

  private emit<K extends keyof EventMap>(event: K, data: EventMap[K]) {
    const listeners = this.listeners.get(event) as Set<Listener<K>> | undefined;
    if (listeners) {
      for (const listener of listeners) {
        listener(data);
      }
    }
  }

  start() {
    if (this.isRunning) return;
    this.isRunning = true;
    this.isPaused = false;
    this.startTime = Date.now();
    this.elapsedBeforePause = 0;

    this.agendaState = {
      items: structuredClone(this.scenario.agendaItems),
      activeItemId: null,
      startTime: this.startTime,
      totalElapsedSeconds: 0,
    };

    this.emit("speakers", this.scenario.speakers);
    this.emit("agenda", { ...this.agendaState });
    this.emit("captureState", CaptureState.Capturing);

    this.scheduleEvents();
  }

  private scheduleEvents() {
    for (const event of this.scenario.events) {
      const delay = event.timeMs / this.speed;
      const timer = setTimeout(() => {
        if (!this.isRunning || this.isPaused) return;
        this.processEvent(event);
      }, delay - this.elapsedBeforePause);
      this.timers.push(timer);
    }
  }

  private processEvent(event: ScenarioEvent) {
    const action = event.action;

    switch (action.type) {
      case "transcript":
      case "transcript_partial":
        this.emit("transcript", action.segment);
        break;
      case "agenda_transition":
        this.transitionAgenda(action.itemId, action.status);
        break;
      case "hint":
        this.emit("hint", action.hint);
        break;
    }
  }

  private transitionAgenda(itemId: string, status: AgendaItemStatus) {
    const elapsed = this.getElapsedMs() / 1000;

    if (status === AgendaItemStatus.Active && this.agendaState.activeItemId) {
      const prevItem = this.agendaState.items.find(
        (i) => i.id === this.agendaState.activeItemId,
      );
      if (prevItem && prevItem.status === AgendaItemStatus.Active) {
        prevItem.status = AgendaItemStatus.Covered;
      }
    }

    const item = this.agendaState.items.find((i) => i.id === itemId);
    if (item) {
      item.status = status;
      if (status === AgendaItemStatus.Active) {
        this.agendaState.activeItemId = itemId;
      }
    }

    this.agendaState.totalElapsedSeconds = elapsed;

    for (const agItem of this.agendaState.items) {
      if (agItem.id === this.agendaState.activeItemId) {
        agItem.elapsedSeconds += 1;
      }
    }

    this.emit("agenda", { ...this.agendaState, items: [...this.agendaState.items] });
  }

  private getElapsedMs(): number {
    if (this.isPaused) return this.elapsedBeforePause;
    return (Date.now() - this.startTime) * this.speed + this.elapsedBeforePause;
  }

  pause() {
    if (!this.isRunning || this.isPaused) return;
    this.isPaused = true;
    this.pausedAt = Date.now();
    this.elapsedBeforePause = this.getElapsedMs();
    this.clearTimers();
    this.emit("captureState", CaptureState.Paused);
  }

  resume() {
    if (!this.isRunning || !this.isPaused) return;
    this.isPaused = false;
    this.startTime = Date.now();
    this.scheduleEvents();
    this.emit("captureState", CaptureState.Capturing);
  }

  stop() {
    this.isRunning = false;
    this.isPaused = false;
    this.clearTimers();
    this.emit("captureState", CaptureState.Stopped);
    this.emit("done", undefined as never);
  }

  reset() {
    this.stop();
    this.agendaState = {
      items: structuredClone(this.scenario.agendaItems),
      activeItemId: null,
      startTime: 0,
      totalElapsedSeconds: 0,
    };
    this.emit("agenda", { ...this.agendaState });
    this.emit("captureState", CaptureState.Idle);
  }

  setSpeed(speed: number) {
    const wasRunning = this.isRunning && !this.isPaused;
    if (wasRunning) {
      this.elapsedBeforePause = this.getElapsedMs();
      this.clearTimers();
    }
    this.speed = speed;
    if (wasRunning) {
      this.startTime = Date.now();
      this.scheduleEvents();
    }
  }

  private clearTimers() {
    for (const t of this.timers) clearTimeout(t);
    this.timers = [];
  }
}
