import type { TranscriptSegment } from "@/types/transcript";

export type CaptionCallback = (segment: TranscriptSegment) => void;

const LOCAL_USER_NAMES = new Set(["you", "ви", "вы"]);

const STABILITY_MS = 1000;
const REDISCOVER_INTERVAL_MS = 1500;
const SEEN_TTL_MS = 10 * 60 * 1000;

const CC_ON_SELECTORS = [
  'button[aria-label="Turn on captions"]',
  '[role="button"][aria-label="Turn on captions"]',
  'button[aria-label="Увімкнути субтитри"]',
  '[role="button"][aria-label="Увімкнути субтитри"]',
  'button[aria-label="Включить субтитры"]',
  '[role="button"][aria-label="Включить субтитры"]',
];

const CAPTION_REGION_LABELS = [
  "Captions",
  "Субтитри",
  "Субтитры",
  "Untertitel",
  "Sous-titres",
  "Napisy",
];

interface PendingRow {
  speaker: string;
  text: string;
  segmentId: string;
  timestamp: number;
  lastUpdated: number;
}

export class MeetCaptionObserver {
  private observer: MutationObserver | null = null;
  private rediscoverTimer: ReturnType<typeof setInterval> | null = null;
  private captionContainer: Element | null = null;
  private nodeKeys = new WeakMap<Element, string>();
  private nodeKeyCounter = 0;
  private pendingRows = new Map<string, PendingRow>();
  private committedTexts = new Map<string, { speaker: string; text: string }>();
  private seenHashes = new Map<string, number>();
  private segmentCounter = 0;
  private meetingId = "";
  private callbacks: Set<CaptionCallback> = new Set();
  private skipLocalUser = true;
  private localUserName: string | null = null;
  private enableAttempts = 0;
  private lastEnableAt = 0;
  private isRunning = false;

  setMeetingId(meetingId: string): void {
    this.meetingId = meetingId;
  }

  setSkipLocalUser(skip: boolean): void {
    this.skipLocalUser = skip;
  }

  setLocalUserName(name: string | null): void {
    this.localUserName = name ? name.toLowerCase() : null;
  }

  private isLocalSpeaker(speaker: string): boolean {
    const s = speaker.toLowerCase();
    return LOCAL_USER_NAMES.has(s) || (this.localUserName !== null && s === this.localUserName);
  }

  onCaption(callback: CaptionCallback): () => void {
    this.callbacks.add(callback);
    return () => this.callbacks.delete(callback);
  }

  start(): void {
    if (this.isRunning) return;
    this.isRunning = true;
    this.startObserving();
    console.log("[MeetCaptions] Started");
  }

  stop(): void {
    this.isRunning = false;
    this.stopObserving();
    for (const [key, row] of this.pendingRows) {
      this.commitRow(key, row.speaker, row.text, row.segmentId, row.timestamp);
    }
    this.pendingRows.clear();
    this.committedTexts.clear();
    this.captionContainer = null;
    console.log("[MeetCaptions] Stopped");
  }

  tryEnableCaptions(): void {
    this.toggleCaptionsRetry(0);
  }

  private retryEnableCaptions(): void {
    const now = Date.now();
    if (this.enableAttempts >= 12 || now - this.lastEnableAt < 4000) return;
    this.enableAttempts++;
    this.lastEnableAt = now;
    this.toggleCaptionsRetry(7);
  }

  private toggleCaptionsRetry(attempt: number): void {
    if (attempt >= 8) return;
    for (const sel of CC_ON_SELECTORS) {
      const btn = document.querySelector(sel) as HTMLElement | null;
      if (btn && this.isVisible(btn)) {
        btn.click();
        console.log("[MeetCaptions] Enabled captions via", sel);
        return;
      }
    }
    const allBtns = document.querySelectorAll('button, [role="button"]');
    for (const el of allBtns) {
      const label = (el.getAttribute("aria-label") || "").toLowerCase();
      const pressed = el.getAttribute("aria-pressed");
      const icon = el.querySelector("i");
      const iconText = icon ? (icon.textContent || "").trim().toLowerCase() : "";
      if (
        (iconText === "closed_caption_off" || iconText === "closed_caption") &&
        pressed === "false" &&
        this.isVisible(el as HTMLElement)
      ) {
        (el as HTMLElement).click();
        console.log("[MeetCaptions] Enabled captions via icon button");
        return;
      }
      if (
        (label.includes("caption") || label.includes("субтитр")) &&
        pressed === "false" &&
        this.isVisible(el as HTMLElement)
      ) {
        (el as HTMLElement).click();
        console.log("[MeetCaptions] Enabled captions via label:", label);
        return;
      }
    }
    setTimeout(() => this.toggleCaptionsRetry(attempt + 1), 300);
  }

  private isVisible(el: HTMLElement): boolean {
    if (!el.isConnected) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  private rowKey(node: Element): string {
    let id = this.nodeKeys.get(node);
    if (!id) {
      this.nodeKeyCounter++;
      id = `cc-${this.nodeKeyCounter}`;
      this.nodeKeys.set(node, id);
    }
    return id;
  }

  private findCaptionContainer(): Element | null {
    try {
      for (const label of CAPTION_REGION_LABELS) {
        const region = document.querySelector(
          `[role="region"][aria-label="${label}"]`,
        );
        if (region) {
          this.hideCaptionContainer(region as HTMLElement);
          return region;
        }
      }
      // Fallback: any region whose aria-label contains "caption" or "субтитр"
      const allRegions = document.querySelectorAll('[role="region"]');
      for (const region of allRegions) {
        const label = (region.getAttribute("aria-label") || "").toLowerCase();
        if (label.includes("caption") || label.includes("субтитр") || label.includes("untertitel")) {
          this.hideCaptionContainer(region as HTMLElement);
          return region;
        }
      }
    } catch { /* skip */ }
    return null;
  }

  private hideCaptionContainer(container: HTMLElement): void {
    // Hide native captions visually but keep DOM alive so we can scrape
    if (container.dataset.maHidden) return;
    container.dataset.maHidden = "1";
    container.style.position = "fixed";
    container.style.opacity = "0";
    container.style.pointerEvents = "none";
    container.style.zIndex = "-1";
  }

  private isProfileImg(img: Element): boolean {
    if (img.tagName !== "IMG") return false;
    const src = (img.getAttribute("src") || "").trim();
    return src.length > 0 && (src.startsWith("http") || src.startsWith("data:"));
  }

  private parseCaptionRow(
    rowWrapper: Element,
  ): { speaker: string; text: string } | null {
    const img = rowWrapper.querySelector("img");
    if (img && this.isProfileImg(img)) {
      const speakerDiv = img.nextElementSibling;
      const transcriptDiv =
        img.parentElement && img.parentElement.nextElementSibling;
      if (!transcriptDiv) return null;
      const text = (transcriptDiv.textContent || "").replace(/\s+/g, " ").trim();
      if (!text) return null;
      const speaker = speakerDiv
        ? (speakerDiv.textContent || "").replace(/\s+/g, " ").trim()
        : "";
      return { speaker, text };
    }

    const childDivs = rowWrapper.querySelectorAll(":scope > div, :scope > span");
    if (childDivs.length >= 2) {
      const speaker = (childDivs[0].textContent || "").trim();
      const textParts: string[] = [];
      for (let i = 1; i < childDivs.length; i++) {
        const t = (childDivs[i].textContent || "").trim();
        if (t) textParts.push(t);
      }
      const text = textParts.join(" ");
      if (speaker && text && speaker.length < 60) {
        return { speaker, text };
      }
    }

    return null;
  }

  private getCaptionCandidates(container: Element): Element[] {
    const seen = new Set<Element>();
    const candidates: Element[] = [];

    const imgs = container.querySelectorAll("img");
    for (const img of imgs) {
      if (!this.isProfileImg(img)) continue;
      const transcriptDiv =
        img.parentElement && img.parentElement.nextElementSibling;
      if (
        !transcriptDiv ||
        !(transcriptDiv.textContent || "").trim()
      )
        continue;
      const rowWrapper =
        img.parentElement && img.parentElement.parentElement;
      if (!rowWrapper || seen.has(rowWrapper)) continue;
      if (rowWrapper.closest("button")) continue;
      seen.add(rowWrapper);
      if (this.parseCaptionRow(rowWrapper)) candidates.push(rowWrapper);
    }

    if (candidates.length > 0) return candidates;

    for (const child of container.children) {
      if (this.parseCaptionRow(child)) {
        candidates.push(child);
      } else {
        for (const grandchild of child.children) {
          if (this.parseCaptionRow(grandchild)) candidates.push(grandchild);
        }
      }
    }
    return candidates;
  }

  private processContainer(container: Element): void {
    const candidates = this.getCaptionCandidates(container);
    const currentKeys = new Set<string>();
    const now = Date.now();

    for (const node of candidates) {
      const parsed = this.parseCaptionRow(node);
      if (!parsed) continue;

      if (this.skipLocalUser && this.isLocalSpeaker(parsed.speaker)) continue;

      const key = this.rowKey(node);
      currentKeys.add(key);

      // Already committed rows stay in the DOM for a while: only emit new growth.
      const committed = this.committedTexts.get(key);
      if (committed) {
        if (committed.speaker === parsed.speaker && committed.text === parsed.text) continue;
        if (committed.speaker === parsed.speaker && parsed.text.startsWith(committed.text)) {
          parsed.text = parsed.text.slice(committed.text.length).trim();
          if (!parsed.text) continue;
        }
        this.committedTexts.delete(key);
      }

      const existing = this.pendingRows.get(key);
      if (existing) {
        if (existing.text !== parsed.text || existing.speaker !== parsed.speaker) {
          existing.speaker = parsed.speaker;
          existing.text = parsed.text;
          existing.lastUpdated = now;

          this.emitSegment({
            id: existing.segmentId,
            meetingId: this.meetingId,
            speakerId: parsed.speaker,
            text: parsed.text,
            timestamp: existing.timestamp,
            isFinal: false,
            version: 0,
          });
        }
        if (now - existing.lastUpdated >= STABILITY_MS) {
          this.commitRow(key, existing.speaker, existing.text, existing.segmentId, existing.timestamp);
          this.pendingRows.delete(key);
        }
      } else {
        const segmentId = this.generateSegmentId();
        this.pendingRows.set(key, {
          speaker: parsed.speaker,
          text: parsed.text,
          segmentId,
          timestamp: now,
          lastUpdated: now,
        });
        this.emitSegment({
          id: segmentId,
          meetingId: this.meetingId,
          speakerId: parsed.speaker,
          text: parsed.text,
          timestamp: now,
          isFinal: false,
          version: 0,
        });
      }
    }

    for (const [key, row] of this.pendingRows) {
      if (!currentKeys.has(key)) {
        this.commitRow(key, row.speaker, row.text, row.segmentId, row.timestamp);
        this.pendingRows.delete(key);
        this.committedTexts.delete(key);
      }
    }
  }

  private commitRow(
    key: string,
    speaker: string,
    text: string,
    segmentId: string,
    timestamp: number,
  ): void {
    if (!text) return;

    const hash = `${speaker}\n${text}`;
    const seenAt = this.seenHashes.get(hash);
    if (seenAt && Date.now() - seenAt < SEEN_TTL_MS) return;
    this.seenHashes.set(hash, Date.now());

    const prev = this.committedTexts.get(key);
    const full = prev && prev.speaker === speaker ? `${prev.text} ${text}`.trim() : text;
    this.committedTexts.set(key, { speaker, text: full });
    this.emitSegment({
      id: segmentId,
      meetingId: this.meetingId,
      speakerId: speaker,
      text,
      timestamp,
      isFinal: true,
      confidence: 0.85,
      version: 1,
    });
  }

  private startObserving(): void {
    const discover = () => {
      if (!this.isRunning) return;
      if (this.captionContainer && !document.contains(this.captionContainer)) {
        this.captionContainer = null;
      }
      if (!this.captionContainer) {
        this.captionContainer = this.findCaptionContainer();
      }
      if (!this.captionContainer) this.retryEnableCaptions();
      if (this.captionContainer) {
        this.processContainer(this.captionContainer);
      }
    };

    discover();

    this.observer = new MutationObserver(() => {
      if (!this.isRunning) return;
      if (this.captionContainer && document.contains(this.captionContainer)) {
        this.processContainer(this.captionContainer);
      } else {
        this.captionContainer = this.findCaptionContainer();
        if (this.captionContainer) this.processContainer(this.captionContainer);
      }
    });

    this.observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    this.rediscoverTimer = setInterval(() => {
      if (!this.isRunning) return;
      this.pruneSeenHashes();
      discover();
    }, REDISCOVER_INTERVAL_MS);
  }

  private stopObserving(): void {
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
    }
    if (this.rediscoverTimer) {
      clearInterval(this.rediscoverTimer);
      this.rediscoverTimer = null;
    }
  }

  private pruneSeenHashes(): void {
    const now = Date.now();
    for (const [hash, ts] of this.seenHashes) {
      if (now - ts > SEEN_TTL_MS) this.seenHashes.delete(hash);
    }
  }

  private generateSegmentId(): string {
    this.segmentCounter++;
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    return `cap-${Date.now()}-${this.segmentCounter}`;
  }

  private emitSegment(segment: TranscriptSegment): void {
    for (const cb of this.callbacks) {
      try {
        cb(segment);
      } catch (err) {
        console.error("[MeetCaptions] Callback error:", err);
      }
    }
  }
}
