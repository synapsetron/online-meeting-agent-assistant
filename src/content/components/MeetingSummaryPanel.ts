import type { MeetingReport, MeetingStats, MeetingSummaryPayload } from "@/types/summary";
import { el, formatTime } from "../utils/dom";
import { CollapsibleSection } from "./CollapsibleSection";

/** How long to wait for the backend before telling the user nothing is coming. */
const RESPONSE_TIMEOUT_MS = 45_000;

const FALLBACK_NOTES: Record<string, string> = {
  disabled: "AI summary is turned off on the backend.",
  too_short: "Too little was said to write a summary.",
  budget: "AI summary skipped: the session cost limit was reached.",
  llm_unavailable: "AI summary is unavailable right now (check the API key and backend log).",
  invalid_output: "AI summary could not be validated and was discarded.",
  truncated_output: "AI summary was cut off and was discarded.",
};

function speakerName(speakerId: string): string {
  return speakerId === "local-user" ? "You" : speakerId;
}

function percent(share: number): string {
  return `${Math.round(share * 100)}%`;
}

export class MeetingSummaryPanel {
  readonly root: HTMLElement;
  private section: CollapsibleSection;
  private body: HTMLElement;
  private timeout: ReturnType<typeof setTimeout> | null = null;
  private lastPayload: MeetingSummaryPayload | null = null;

  constructor() {
    this.section = new CollapsibleSection("Meeting summary", "Meeting summary section");
    this.section.setBadge("");
    this.body = el("div", { className: "ma-summary" });
    this.section.content.appendChild(this.body);
    this.root = this.section.root;
    this.root.style.display = "none";
  }

  /** Called when the user stops capture, before the backend has answered. */
  showPending() {
    this.root.style.display = "";
    this.lastPayload = null;
    this.body.replaceChildren(this.statusLine("Preparing meeting statistics…", true));
    this.armTimeout("No response from the backend, so no statistics are available.");
  }

  update(payload: MeetingSummaryPayload) {
    this.root.style.display = "";
    this.lastPayload = payload;
    this.clearTimeout();

    const children: Node[] = [];
    if (payload.stats) children.push(...this.renderStats(payload.stats));

    if (payload.pending) {
      children.push(this.statusLine("Writing the summary…", true));
      this.armTimeout("The summary did not arrive from the backend.");
    } else if (payload.report) {
      children.push(...this.renderReport(payload.report));
    }

    if (!payload.pending && (payload.stats || payload.report)) {
      children.push(this.copyButton());
    }
    this.body.replaceChildren(...children);
  }

  clear() {
    this.clearTimeout();
    this.lastPayload = null;
    this.body.replaceChildren();
    this.root.style.display = "none";
  }

  destroy() {
    this.clearTimeout();
  }

  private armTimeout(message: string) {
    this.clearTimeout();
    this.timeout = setTimeout(() => {
      const pending = this.body.querySelector(".ma-summary-status");
      pending?.replaceWith(this.statusLine(message, false));
    }, RESPONSE_TIMEOUT_MS);
  }

  private clearTimeout() {
    if (this.timeout) {
      clearTimeout(this.timeout);
      this.timeout = null;
    }
  }

  private statusLine(text: string, busy: boolean): HTMLElement {
    return el("div", {
      className: `ma-summary-status${busy ? " busy" : ""}`,
      role: "status",
      textContent: text,
    });
  }

  private heading(text: string): HTMLElement {
    return el("div", { className: "ma-summary-heading", textContent: text });
  }

  private barRow(label: string, share: number, detail: string, title?: string): HTMLElement {
    const fill = el("div", { className: "ma-summary-bar-fill" });
    fill.style.width = `${Math.max(0, Math.min(100, share * 100))}%`;
    const labelEl = el("span", { className: "ma-summary-row-label", textContent: label });
    if (title) labelEl.title = title;
    return el("div", { className: "ma-summary-row" }, [
      el("div", { className: "ma-summary-row-head" }, [
        labelEl,
        el("span", { className: "ma-summary-row-detail", textContent: detail }),
      ]),
      el("div", { className: "ma-summary-bar" }, [fill]),
    ]);
  }

  private renderStats(stats: MeetingStats): Node[] {
    const nodes: Node[] = [];

    nodes.push(
      el("div", { className: "ma-summary-totals" }, [
        this.total(formatTime(stats.durationSeconds), "duration"),
        this.total(String(stats.totalWords), "words"),
        this.total(String(stats.speakers.length), stats.speakers.length === 1 ? "speaker" : "speakers"),
        this.total(String(stats.hintsShown), stats.hintsShown === 1 ? "hint" : "hints"),
      ]),
    );

    nodes.push(this.heading("Who spoke"));
    if (stats.speakers.length === 0) {
      nodes.push(el("div", { className: "ma-summary-empty", textContent: "No speech was transcribed." }));
    }
    for (const speaker of stats.speakers) {
      nodes.push(
        this.barRow(
          speakerName(speaker.speakerId),
          speaker.share,
          `${percent(speaker.share)} · ${speaker.words} words`,
        ),
      );
    }

    nodes.push(this.heading("Topics"));
    for (const item of stats.agenda) {
      const isOffAgenda = item.itemId === null;
      const time = isOffAgenda ? "" : `${formatTime(item.elapsedSeconds)} · `;
      const status = isOffAgenda || item.status === "pending" ? "" : ` · ${item.status}`;
      nodes.push(
        this.barRow(
          item.title,
          item.share,
          item.words === 0 && item.elapsedSeconds === 0
            ? "not discussed"
            : `${time}${percent(item.share)} of talk${status}`,
          item.title,
        ),
      );
    }
    nodes.push(
      el("div", {
        className: "ma-summary-footnote",
        textContent: "Shares are measured in transcribed words. Topic time is how long the item was active.",
      }),
    );
    return nodes;
  }

  private total(value: string, label: string): HTMLElement {
    return el("div", { className: "ma-summary-total" }, [
      el("div", { className: "ma-summary-total-value", textContent: value }),
      el("div", { className: "ma-summary-total-label", textContent: label }),
    ]);
  }

  private list(title: string, items: string[]): Node[] {
    if (items.length === 0) return [];
    return [
      this.heading(title),
      el("ul", { className: "ma-summary-list" }, items.map((text) => el("li", { textContent: text }))),
    ];
  }

  private renderReport(report: MeetingReport): Node[] {
    if (report.source === "fallback") {
      const text = FALLBACK_NOTES[report.note ?? ""] ?? "AI summary is not available.";
      return [this.heading("Summary"), this.statusLine(text, false)];
    }
    const nodes: Node[] = [
      this.heading("Summary"),
      el("p", { className: "ma-summary-text", textContent: report.summary }),
      ...this.list("Key points", report.keyPoints),
      ...this.list("Decisions", report.decisions),
      ...this.list(
        "Action items",
        report.actionItems.map((a) => (a.owner ? `${a.task} — ${a.owner}` : a.task)),
      ),
      ...this.list("Open questions", report.openQuestions),
    ];
    const notes = ["Written by AI from the transcript; check before relying on it."];
    if (report.truncated) notes.push("The meeting was long, so the middle part was not included.");
    nodes.push(el("div", { className: "ma-summary-footnote", textContent: notes.join(" ") }));
    return nodes;
  }

  private copyButton(): HTMLElement {
    const button = el("button", {
      className: "ma-btn-sm ma-summary-copy",
      type: "button",
      textContent: "Copy summary",
    });
    button.addEventListener("click", () => {
      navigator.clipboard
        .writeText(this.asText())
        .then(() => {
          button.textContent = "Copied";
        })
        .catch(() => {
          button.textContent = "Copy failed";
        })
        .finally(() => {
          setTimeout(() => {
            button.textContent = "Copy summary";
          }, 1500);
        });
    });
    return button;
  }

  private asText(): string {
    const payload = this.lastPayload;
    if (!payload) return "";
    const lines: string[] = [];
    const { stats, report } = payload;
    if (stats) {
      lines.push(`Meeting: ${formatTime(stats.durationSeconds)}, ${stats.totalWords} words`);
      lines.push("", "Who spoke:");
      for (const s of stats.speakers) {
        lines.push(`- ${speakerName(s.speakerId)}: ${percent(s.share)} (${s.words} words)`);
      }
      lines.push("", "Topics:");
      for (const a of stats.agenda) {
        const time = a.itemId === null ? "" : `${formatTime(a.elapsedSeconds)}, `;
        lines.push(`- ${a.title}: ${time}${percent(a.share)} of talk`);
      }
    }
    if (report && report.source === "llm") {
      lines.push("", "Summary:", report.summary);
      const section = (title: string, items: string[]) => {
        if (items.length) lines.push("", `${title}:`, ...items.map((i) => `- ${i}`));
      };
      section("Key points", report.keyPoints);
      section("Decisions", report.decisions);
      section(
        "Action items",
        report.actionItems.map((a) => (a.owner ? `${a.task} — ${a.owner}` : a.task)),
      );
      section("Open questions", report.openQuestions);
    }
    return lines.join("\n");
  }
}
