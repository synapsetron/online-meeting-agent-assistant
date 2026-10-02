import type { AgendaState } from "@/types/agenda";
import { AgendaItemStatus } from "@/types/agenda";
import { el, formatTime } from "../utils/dom";

const STATUS_ICONS: Record<AgendaItemStatus, string> = {
  [AgendaItemStatus.Pending]: "",
  [AgendaItemStatus.Active]: "▶",
  [AgendaItemStatus.Covered]: "✓",
  [AgendaItemStatus.Deferred]: "↻",
  [AgendaItemStatus.Skipped]: "—",
};

export class AgendaTracker {
  readonly root: HTMLElement;
  private section: HTMLElement;
  private sectionContent: HTMLElement;
  private progressBar: HTMLElement;
  private list: HTMLElement;
  private badge: HTMLElement;
  private chevron: HTMLElement;
  private isOpen = true;
  private timerInterval: ReturnType<typeof setInterval> | null = null;
  private activeTimeEl: HTMLElement | null = null;
  private activeStartTime = 0;
  private activeElapsed = 0;

  constructor() {
    this.chevron = el("span", { className: "ma-section-chevron open", textContent: "▸" });
    this.badge = el("span", { className: "ma-section-badge", textContent: "0/0" });

    const header = el("div", {
      className: "ma-section-header",
      role: "button",
      tabindex: "0",
      "aria-expanded": "true",
      "aria-label": "Agenda section",
    }, [
      this.chevron,
      el("span", { className: "ma-section-title", textContent: "Agenda" }),
      this.badge,
    ]);

    header.addEventListener("click", () => this.toggle());
    header.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        this.toggle();
      }
    });

    this.progressBar = el("div", { className: "ma-progress-bar" });
    this.list = el("ul", { className: "ma-agenda-list" });

    this.sectionContent = el("div", { className: "ma-section-content" }, [
      this.progressBar,
      this.list,
    ]);

    this.section = el("div", { className: "ma-section" }, [header, this.sectionContent]);
    this.root = this.section;
  }

  private toggle() {
    this.isOpen = !this.isOpen;
    this.chevron.className = `ma-section-chevron${this.isOpen ? " open" : ""}`;
    this.sectionContent.className = `ma-section-content${this.isOpen ? "" : " closed"}`;
    const header = this.section.querySelector(".ma-section-header");
    header?.setAttribute("aria-expanded", String(this.isOpen));
  }

  update(state: AgendaState) {
    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }

    const covered = state.items.filter(
      (i) => i.status === AgendaItemStatus.Covered,
    ).length;
    this.badge.textContent = `${covered}/${state.items.length}`;

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

      const timeText =
        item.status === AgendaItemStatus.Active
          ? formatTime(item.elapsedSeconds)
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
        this.activeElapsed = item.elapsedSeconds;
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
        const extra = Math.floor((Date.now() - this.activeStartTime) / 1000);
        this.activeTimeEl.textContent = formatTime(this.activeElapsed + extra);
      }, 1000);
    }
  }

  destroy() {
    if (this.timerInterval) clearInterval(this.timerInterval);
  }
}
