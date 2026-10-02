import type { TranscriptSegment, Speaker } from "@/types/transcript";
import { el, formatTimestamp } from "../utils/dom";
import { MAX_VISIBLE_SEGMENTS } from "@/shared/constants";

export class TranscriptPanel {
  readonly root: HTMLElement;
  private section: HTMLElement;
  private sectionContent: HTMLElement;
  private list: HTMLElement;
  private badge: HTMLElement;
  private chevron: HTMLElement;
  private isOpen = true;
  private isCapturing = false;
  private segments: TranscriptSegment[] = [];
  private speakers: Map<string, Speaker> = new Map();
  private userScrolled = false;

  constructor() {
    this.chevron = el("span", { className: "ma-section-chevron open", textContent: "▸" });
    this.badge = el("span", { className: "ma-section-badge", textContent: "0" });

    const liveIndicator = el("span", {
      className: "ma-transcript-live-dot",
      "aria-label": "Live",
    });
    liveIndicator.style.display = "none";

    const headerContent = el("span", { className: "ma-section-title" }, [
      document.createTextNode("Transcript"),
      liveIndicator,
    ]);

    const header = el("div", {
      className: "ma-section-header",
      role: "button",
      tabindex: "0",
      "aria-expanded": "true",
      "aria-label": "Transcript section",
    }, [this.chevron, headerContent, this.badge]);

    header.addEventListener("click", () => this.toggle());
    header.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        this.toggle();
      }
    });

    this.list = el("div", { className: "ma-transcript-list" });
    this.list.innerHTML = `<div class="ma-transcript-empty">Waiting for transcript...</div>`;

    this.list.addEventListener("scroll", () => {
      const { scrollTop, scrollHeight, clientHeight } = this.list;
      this.userScrolled = scrollHeight - scrollTop - clientHeight > 30;
    });

    this.sectionContent = el("div", { className: "ma-section-content" }, [this.list]);
    this.section = el("div", { className: "ma-section" }, [header, this.sectionContent]);
    this.root = this.section;
  }

  private toggle() {
    this.isOpen = !this.isOpen;
    this.chevron.className = `ma-section-chevron${this.isOpen ? " open" : ""}`;
    this.sectionContent.className = `ma-section-content${this.isOpen ? "" : " closed"}`;
  }

  setSpeakers(speakers: Speaker[]) {
    this.speakers.clear();
    for (const s of speakers) {
      this.speakers.set(s.id, s);
    }
  }

  setCapturing(capturing: boolean) {
    this.isCapturing = capturing;
    const liveDot = this.root.querySelector(".ma-transcript-live-dot") as HTMLElement | null;
    if (liveDot) liveDot.style.display = capturing ? "" : "none";
  }

  addSegment(segment: TranscriptSegment) {
    const existing = this.segments.findIndex((s) => s.id === segment.id);
    if (existing >= 0) {
      if (segment.version > this.segments[existing].version) {
        this.segments[existing] = segment;
        this.updateSegmentElement(segment);
      }
      return;
    }

    this.segments.push(segment);

    if (this.segments.length > MAX_VISIBLE_SEGMENTS) {
      this.segments.shift();
      const firstChild = this.list.firstElementChild;
      if (firstChild && !firstChild.classList.contains("ma-transcript-empty")) {
        firstChild.remove();
      }
    }

    if (this.segments.length === 1) {
      this.list.innerHTML = "";
    }

    const segEl = this.createSegmentElement(segment);
    this.list.appendChild(segEl);

    this.badge.textContent = String(this.segments.length);

    if (!this.userScrolled) {
      this.list.scrollTop = this.list.scrollHeight;
    }
  }

  private createSegmentElement(segment: TranscriptSegment): HTMLElement {
    const speaker = this.speakers.get(segment.speakerId);
    const speakerName = el("span", {
      className: "ma-transcript-speaker",
      textContent: speaker?.name ?? "Unknown",
    });
    if (speaker) speakerName.style.color = speaker.color;

    const time = el("span", {
      className: "ma-transcript-time",
      textContent: formatTimestamp(segment.timestamp),
    });

    const speakerRow = el("div", { className: "ma-transcript-speaker-row" }, [
      speakerName,
      time,
    ]);

    const text = el("div", {
      className: `ma-transcript-text${segment.isFinal ? "" : " partial"}`,
      textContent: segment.text,
    });

    const container = el("div", {
      className: "ma-transcript-segment",
      "data-segment-id": segment.id,
    }, [speakerRow, text]);

    return container;
  }

  private updateSegmentElement(segment: TranscriptSegment) {
    const el = this.list.querySelector(
      `[data-segment-id="${segment.id}"]`,
    ) as HTMLElement | null;
    if (!el) return;

    const textEl = el.querySelector(".ma-transcript-text");
    if (textEl) {
      textEl.textContent = segment.text;
      textEl.className = `ma-transcript-text${segment.isFinal ? "" : " partial"}`;
    }
  }

  destroy() {
    this.segments = [];
  }
}
