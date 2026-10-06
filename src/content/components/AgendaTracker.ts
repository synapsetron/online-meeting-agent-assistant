import type { AgendaState } from "@/types/agenda";
import { AgendaItemStatus } from "@/types/agenda";
import { el, formatTime } from "../utils/dom";
import { CollapsibleSection } from "./CollapsibleSection";

const STATUS_ICONS: Record<AgendaItemStatus, string> = {
  [AgendaItemStatus.Pending]: "",
  [AgendaItemStatus.Active]: "▶",
  [AgendaItemStatus.Covered]: "✓",
  [AgendaItemStatus.Deferred]: "↻",
  [AgendaItemStatus.Skipped]: "—",
};

export class AgendaTracker {
  readonly root: HTMLElement;
  private section: CollapsibleSection;
  private progressBar: HTMLElement;
  private list: HTMLElement;
  private timerInterval: ReturnType<typeof setInterval> | null = null;
  private activeTimeEl: HTMLElement | null = null;
  private activeStartTime = 0;
  private activeElapsed = 0;
  private activeItemId: string | null = null;

  constructor() {
    this.section = new CollapsibleSection("Agenda", "Agenda section");

    this.progressBar = el("div", { className: "ma-progress-bar" });
    this.list = el("ul", { className: "ma-agenda-list" });

    this.section.content.appendChild(this.progressBar);
    this.section.content.appendChild(this.list);

    this.root = this.section.root;
  }

  private currentElapsed(): number {
    return this.activeElapsed + Math.floor((Date.now() - this.activeStartTime) / 1000);
  }

  update(state: AgendaState) {
    // Keep the running local clock if the same item is still active and the
    // server value is not ahead of it, so periodic syncs don't restart the timer.
    const running = this.activeItemId !== null ? this.currentElapsed() : 0;
    const previousId = this.activeItemId;
    this.activeItemId = null;

    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }

    const covered = state.items.filter(
      (i) => i.status === AgendaItemStatus.Covered,
    ).length;
    this.section.setBadge(`${covered}/${state.items.length}`);

    this.progressBar.innerHTML = "";
    for (const item of state.items) {
      const seg = el("div", {
        className: `ma-progress-segment ${item.status}`,
      });
      this.progressBar.appendChild(seg);
    }

    this.list.innerHTML = "";
    this.activeTimeEl = null;

    for (const item of state.items) {
      const icon = el("div", {
        className: `ma-agenda-icon ${item.status}`,
        textContent: STATUS_ICONS[item.status],
      });

      const title = el("span", {
        className: "ma-agenda-title",
        textContent: item.title,
        title: item.description ?? item.title,
      });

      const keepLocal =
        item.status === AgendaItemStatus.Active &&
        item.id === previousId &&
        running >= item.elapsedSeconds;
      const shown = keepLocal ? running : item.elapsedSeconds;

      const timeText =
        item.status === AgendaItemStatus.Active
          ? formatTime(shown)
          : item.elapsedSeconds > 0
            ? formatTime(item.elapsedSeconds)
            : item.estimatedMinutes
              ? `~${item.estimatedMinutes}m`
              : "";

      const timeEl = el("span", {
        className: `ma-agenda-time${item.status === AgendaItemStatus.Active ? " active" : ""}`,
        textContent: timeText,
      });

      if (item.status === AgendaItemStatus.Active) {
        this.activeTimeEl = timeEl;
        this.activeStartTime = Date.now();
        this.activeElapsed = shown;
        this.activeItemId = item.id;
      }

      const li = el("li", { className: `ma-agenda-item ${item.status}` }, [
        icon,
        title,
        timeEl,
      ]);

      this.list.appendChild(li);
    }

    if (this.activeTimeEl) {
      this.timerInterval = setInterval(() => {
        if (!this.activeTimeEl) return;
        this.activeTimeEl.textContent = formatTime(this.currentElapsed());
      }, 1000);
    }
  }

  destroy() {
    if (this.timerInterval) clearInterval(this.timerInterval);
  }
}
