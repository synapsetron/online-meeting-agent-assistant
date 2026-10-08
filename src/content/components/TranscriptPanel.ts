import type { TranscriptSegment, Speaker } from "@/types/transcript";
import { el, formatTimestamp } from "../utils/dom";
import { MAX_VISIBLE_SEGMENTS } from "@/shared/constants";
import { CollapsibleSection } from "./CollapsibleSection";

export class TranscriptPanel {
  readonly root: HTMLElement;
  private section: CollapsibleSection;
  private list: HTMLElement;
  private isCapturing = false;
  private segments: TranscriptSegment[] = [];
  private speakers: Map<string, Speaker> = new Map();
  private userScrolled = false;

  constructor() {
    const liveIndicator = el("span", {
      className: "ma-transcript-live-dot",
      "aria-label": "Live",
    });
    liveIndicator.style.display = "none";

    this.section = new CollapsibleSection(
      "Transcript",
      "Transcript section",
      [liveIndicator],
    );

    this.list = el("div", { className: "ma-transcript-list" });
    this.list.innerHTML = `<div class="ma-transcript-empty">Waiting for transcript...</div>`;

    this.list.addEventListener("scroll", () => {
      const { scrollTop, scrollHeight, clientHeight } = this.list;
      this.userScrolled = scrollHeight - scrollTop - clientHeight > 30;
    });

    this.section.content.appendChild(this.list);
    this.root = this.section.root;
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
      this.segments[existing] = segment;
      this.updateSegmentElement(segment);
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

    this.section.setBadge(String(this.segments.length));

    if (!this.userScrolled) {
      this.list.scrollTop = this.list.scrollHeight;
    }
  }

  private createSegmentElement(segment: TranscriptSegment): HTMLElement {
    const speaker = this.speakers.get(segment.speakerId);
    const displayName = speaker?.name ?? (segment.speakerId === "local-user" ? "You" : segment.speakerId);
    const speakerName = el("span", {
      className: "ma-transcript-speaker",
      textContent: displayName,
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
    const segEl = this.list.querySelector(
      `[data-segment-id="${segment.id}"]`,
    ) as HTMLElement | null;
    if (!segEl) return;

    const textEl = segEl.querySelector(".ma-transcript-text");
    if (textEl) {
      textEl.textContent = segment.text;
      textEl.className = `ma-transcript-text${segment.isFinal ? "" : " partial"}`;
    }
  }

  destroy() {
    this.segments = [];
  }
}
