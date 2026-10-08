import type { AgendaState } from "@/types/agenda";
import type { TranscriptSegment, Speaker } from "@/types/transcript";
import type { Hint } from "@/types/hint";
import { CaptureState } from "@/types/meeting";
import { el } from "../utils/dom";
import { makeDraggable, makeResizable } from "../utils/drag";
import { trapFocus, onEscape } from "../utils/keyboard";
import { OVERLAY_WIDTH_MIN, OVERLAY_WIDTH_MAX } from "@/shared/constants";
import { AgendaTracker } from "./AgendaTracker";
import { TranscriptPanel } from "./TranscriptPanel";
import { HintCards } from "./HintCards";
import { CaptureStatusBar } from "./CaptureStatusBar";
import { OverlaySettings } from "./OverlaySettings";
import { MeetingSummaryPanel } from "./MeetingSummaryPanel";
import type { MeetingSummaryPayload } from "@/types/summary";

export class OverlayContainer {
  readonly root: HTMLElement;
  private overlay: HTMLElement;
  private pill: HTMLElement;
  private agendaTracker: AgendaTracker;
  private transcriptPanel: TranscriptPanel;
  private hintCards: HintCards;
  private captureStatusBar: CaptureStatusBar;
  private overlaySettings: OverlaySettings;
  private summaryPanel: MeetingSummaryPanel;
  private bodyEl!: HTMLElement;
  private isMinimized = false;
  private cleanups: (() => void)[] = [];
  private onDismissHint: ((hintId: string) => void) | null = null;
  private onStopCapture: (() => void) | null = null;

  constructor(options?: {
    onDismissHint?: (hintId: string) => void;
    onStopCapture?: () => void;
    onStartCapture?: () => void;
  }) {
    this.onDismissHint = options?.onDismissHint ?? null;
    this.onStopCapture = options?.onStopCapture ?? null;

    this.captureStatusBar = new CaptureStatusBar(
      () => this.onStopCapture?.(),
      () => options?.onStartCapture?.(),
    );
    this.agendaTracker = new AgendaTracker();
    this.transcriptPanel = new TranscriptPanel();
    this.hintCards = new HintCards((id) => this.onDismissHint?.(id));
    this.summaryPanel = new MeetingSummaryPanel();
    this.overlaySettings = new OverlaySettings(() => {
      this.bodyEl.style.display = "";
      this.overlaySettings.root.style.display = "none";
    });

    const titlebarIcon = el("div", { className: "ma-titlebar-icon", textContent: "M" });
    const titlebarText = el("span", { className: "ma-titlebar-text", textContent: "Meeting Assistant" });

    const settingsBtn = el("button", {
      className: "ma-btn-icon ma-btn-settings",
      "aria-label": "Settings",
      textContent: "⚙",
    });
    settingsBtn.addEventListener("pointerdown", (e) => e.stopPropagation());
    settingsBtn.addEventListener("click", () => this.toggleSettings());

    const minimizeBtn = el("button", {
      className: "ma-btn-icon",
      "aria-label": "Minimize panel",
      textContent: "−",
    });
    minimizeBtn.addEventListener("click", () => this.minimize());

    const closeBtn = el("button", {
      className: "ma-btn-icon",
      "aria-label": "Close panel",
      textContent: "✕",
    });
    closeBtn.addEventListener("click", () => this.close());

    const actions = el("div", { className: "ma-titlebar-actions" }, [settingsBtn, minimizeBtn, closeBtn]);
    const titlebar = el("div", { className: "ma-titlebar" }, [titlebarIcon, titlebarText, actions]);

    this.bodyEl = el("div", { className: "ma-body" }, [
      this.summaryPanel.root,
      this.agendaTracker.root,
      this.transcriptPanel.root,
      this.hintCards.root,
    ]);

    const resizeLeft = el("div", { className: "ma-resize-handle" });
    const resizeBottom = el("div", { className: "ma-resize-handle-bottom" });

    this.overlay = el("div", {
      className: "ma-overlay",
      role: "complementary",
      "aria-label": "Meeting Assistant",
    }, [resizeLeft, resizeBottom, titlebar, this.captureStatusBar.root, this.bodyEl, this.overlaySettings.root]);

    this.cleanups.push(
      makeDraggable(
        titlebar,
        this.overlay,
        () => this.overlay.classList.add("dragging"),
        () => this.overlay.classList.remove("dragging"),
      ),
    );

    this.cleanups.push(
      makeResizable(resizeLeft, this.overlay, "horizontal", OVERLAY_WIDTH_MIN, OVERLAY_WIDTH_MAX),
    );

    this.cleanups.push(trapFocus(this.overlay));
    this.cleanups.push(onEscape(this.overlay, () => this.minimize()));

    this.pill = el("div", { className: "ma-pill", role: "button", tabindex: "0", "aria-label": "Open Meeting Assistant" }, [
      el("div", { className: "ma-pill-icon", textContent: "M" }),
      el("span", { className: "ma-pill-status", textContent: "Meeting Assistant" }),
    ]);
    this.pill.style.display = "none";
    this.pill.addEventListener("click", () => this.restore());
    this.pill.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        this.restore();
      }
    });

    this.root = el("div", {}, [this.overlay, this.pill]);
  }

  private minimize() {
    this.isMinimized = true;
    this.overlay.classList.add("collapsed");
    this.pill.style.display = "";
  }

  private restore() {
    this.isMinimized = false;
    this.overlay.classList.remove("collapsed");
    this.pill.style.display = "none";
  }

  private toggleSettings() {
    if (this.overlaySettings.isVisible) {
      this.overlaySettings.hide();
    } else {
      this.bodyEl.style.display = "none";
      this.overlaySettings.show();
    }
  }

  private close() {
    this.root.style.display = "none";
  }

  show() {
    this.root.style.display = "";
    if (this.isMinimized) {
      this.restore();
    }
  }

  updateAgenda(state: AgendaState) {
    this.agendaTracker.update(state);
    this.hintCards.setAgendaItems(state.items);

    const covered = state.items.filter((i) => i.status === "covered").length;
    const pillStatus = this.pill.querySelector(".ma-pill-status");
    if (pillStatus) pillStatus.textContent = `${covered}/${state.items.length} items`;
  }

  setSpeakers(speakers: Speaker[]) {
    this.transcriptPanel.setSpeakers(speakers);
  }

  addTranscript(segment: TranscriptSegment) {
    this.transcriptPanel.addSegment(segment);
  }

  addHint(hint: Hint) {
    this.hintCards.addHint(hint);
  }

  showSummaryPending() {
    this.summaryPanel.showPending();
    this.bodyEl.scrollTop = 0;
  }

  showSummary(payload: MeetingSummaryPayload) {
    this.summaryPanel.update(payload);
    this.bodyEl.scrollTop = 0;
  }

  setCaptureState(state: CaptureState) {
    if (state === CaptureState.Capturing) this.summaryPanel.clear();
    this.captureStatusBar.update(state);
    this.transcriptPanel.setCapturing(state === CaptureState.Capturing);
  }

  destroy() {
    for (const cleanup of this.cleanups) cleanup();
    this.agendaTracker.destroy();
    this.transcriptPanel.destroy();
    this.hintCards.destroy();
    this.captureStatusBar.destroy();
    this.overlaySettings.destroy();
    this.summaryPanel.destroy();
  }
}
