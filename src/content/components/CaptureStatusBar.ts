import { CaptureState } from "@/types/meeting";
import { el, formatTime } from "../utils/dom";

export class CaptureStatusBar {
  readonly root: HTMLElement;
  private dot: HTMLElement;
  private label: HTMLElement;
  private timeEl: HTMLElement;
  private startBtn: HTMLElement;
  private stopBtn: HTMLElement;
  private state: CaptureState = CaptureState.Idle;
  private startTime = 0;
  private timerInterval: ReturnType<typeof setInterval> | null = null;
  private onStop: (() => void) | null = null;
  private onStart: (() => void) | null = null;

  constructor(onStop?: () => void, onStart?: () => void) {
    this.onStop = onStop ?? null;
    this.onStart = onStart ?? null;

    this.dot = el("div", { className: "ma-capture-dot idle" });
    this.label = el("span", { className: "ma-capture-label", textContent: "Not recording" });
    this.timeEl = el("span", { className: "ma-capture-time" });

    this.startBtn = el("button", {
      className: "ma-btn-sm ma-btn-start",
      textContent: "Start",
      "aria-label": "Start capture",
    });
    this.startBtn.addEventListener("click", () => this.onStart?.());

    this.stopBtn = el("button", {
      className: "ma-btn-sm",
      textContent: "Stop",
      "aria-label": "Stop capture",
    });
    this.stopBtn.style.display = "none";
    this.stopBtn.addEventListener("click", () => this.onStop?.());

    this.root = el("div", {
      className: "ma-capture-bar",
      role: "status",
      "aria-label": "Capture status",
    }, [this.dot, this.label, this.timeEl, this.startBtn, this.stopBtn]);
  }

  update(state: CaptureState) {
    this.state = state;

    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }

    this.dot.className = "ma-capture-dot";
    this.startBtn.style.display = "none";
    this.stopBtn.style.display = "none";

    switch (state) {
      case CaptureState.Idle:
        this.dot.classList.add("idle");
        this.label.innerHTML = "Not recording";
        this.timeEl.textContent = "";
        this.startBtn.style.display = "";
        break;
      case CaptureState.Capturing:
        this.startTime = Date.now();
        this.label.innerHTML = "<strong>Recording</strong>";
        this.stopBtn.style.display = "";
        this.timeEl.textContent = "0:00";
        this.timerInterval = setInterval(() => {
          const elapsed = Math.floor((Date.now() - this.startTime) / 1000);
          this.timeEl.textContent = formatTime(elapsed);
        }, 1000);
        break;
      case CaptureState.Paused:
        this.dot.classList.add("idle");
        this.label.innerHTML = "Paused";
        this.stopBtn.style.display = "";
        break;
      case CaptureState.Stopped:
        this.dot.classList.add("stopped");
        this.label.innerHTML = "Session ended";
        this.timeEl.textContent = "";
        this.startBtn.style.display = "";
        break;
    }
  }

  destroy() {
    if (this.timerInterval) clearInterval(this.timerInterval);
  }
}
