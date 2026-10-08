import { ShadowHost } from "../content/shadow-host";
import { OverlayContainer } from "../content/components/OverlayContainer";
import { ThemeManager } from "../content/components/ThemeManager";
import { MeetingSimulator } from "../mock/meeting-simulator";
import { SCENARIOS, type ScenarioName } from "../mock/scenarios";
import { CaptureState } from "../types/meeting";
import type { MeetingReport, MeetingStats } from "../types/summary";

let host: ShadowHost | null = null;
let overlay: OverlayContainer | null = null;
let theme: ThemeManager | null = null;
let sim: MeetingSimulator | null = null;
let isPlaying = false;
let startTimestamp = 0;
let timerInterval: ReturnType<typeof setInterval> | null = null;

const scenarioSelect = document.getElementById("scenarioSelect") as HTMLSelectElement;
const playPauseBtn = document.getElementById("playPauseBtn") as HTMLButtonElement;
const resetBtn = document.getElementById("resetBtn") as HTMLButtonElement;
const speedSelect = document.getElementById("speedSelect") as HTMLSelectElement;
const darkToggle = document.getElementById("darkToggle") as HTMLInputElement;
const mockTime = document.getElementById("mockTime") as HTMLSpanElement;

function formatClock(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function mountOverlay() {
  if (host) {
    host.destroy();
  }

  host = new ShadowHost("open");
  overlay = new OverlayContainer({
    onDismissHint: (id) => console.log("Dismissed hint:", id),
    onStopCapture: () => {
      stopPlayback();
      overlay?.setCaptureState(CaptureState.Stopped);
      playMockSummary();
    },
    onStartCapture: () => startPlayback(),
  });
  host.mount(overlay.root);

  theme = new ThemeManager(host.host);
  theme.init();

  applyTheme();
}

function createSimulator(scenarioName: ScenarioName) {
  if (sim) sim.stop();

  sim = new MeetingSimulator(SCENARIOS[scenarioName]);

  sim.on("speakers", (speakers) => overlay?.setSpeakers(speakers));
  sim.on("agenda", (state) => overlay?.updateAgenda(state));
  sim.on("transcript", (segment) => overlay?.addTranscript(segment));
  sim.on("hint", (hint) => overlay?.addHint(hint));
  sim.on("captureState", (state) => overlay?.setCaptureState(state));
}

function startPlayback() {
  if (!sim) return;
  isPlaying = true;
  playPauseBtn.textContent = "⏸ Pause";
  playPauseBtn.classList.add("active");
  sim.start();
  startTimestamp = Date.now();
  timerInterval = setInterval(() => {
    mockTime.textContent = formatClock(Date.now() - startTimestamp);
  }, 500);
}

function pausePlayback() {
  if (!sim) return;
  isPlaying = false;
  playPauseBtn.textContent = "▶ Play";
  playPauseBtn.classList.remove("active");
  sim.pause();
  if (timerInterval) clearInterval(timerInterval);
}

const MOCK_STATS: MeetingStats = {
  durationSeconds: 1284,
  finalSegments: 142,
  totalWords: 1630,
  hintsShown: 4,
  speakers: [
    { speakerId: "Olena Kovalenko", segments: 61, words: 742, share: 0.4552 },
    { speakerId: "local-user", segments: 48, words: 566, share: 0.3472 },
    { speakerId: "Taras Shevchuk", segments: 33, words: 322, share: 0.1975 },
  ],
  agenda: [
    { itemId: "a1", title: "Sprint results", status: "covered", elapsedSeconds: 412, estimatedMinutes: 5, segments: 50, words: 590, share: 0.362 },
    { itemId: "a2", title: "Release plan and risks for the mobile application", status: "active", elapsedSeconds: 731, estimatedMinutes: 10, segments: 78, words: 905, share: 0.5552 },
    { itemId: "a3", title: "Hiring", status: "pending", elapsedSeconds: 0, segments: 0, words: 0, share: 0 },
    { itemId: null, title: "Outside the agenda", status: "none", elapsedSeconds: 0, segments: 14, words: 135, share: 0.0828 },
  ],
};

const MOCK_REPORT: MeetingReport = {
  source: "llm",
  summary:
    "The team reviewed sprint results and discussed the release plan. The release is moved by one week because of open payment bugs; hiring was not discussed.",
  keyPoints: [
    "Sprint goal was met except for the payment flow.",
    "Two blocking bugs remain in the mobile checkout.",
  ],
  decisions: ["Move the release to next Thursday."],
  actionItems: [
    { task: "Fix the two checkout bugs", owner: "Taras Shevchuk" },
    { task: "Update the release notes", owner: "You" },
    { task: "Schedule a separate call about hiring", owner: null },
  ],
  openQuestions: ["Who signs off the release if QA is not finished?"],
  truncated: false,
};

function playMockSummary() {
  const base = { summary: "", coveredItems: [], missedItems: [] };
  overlay?.showSummaryPending();
  setTimeout(() => overlay?.showSummary({ ...base, stats: MOCK_STATS, pending: true }), 600);
  setTimeout(() => overlay?.showSummary({ ...base, stats: MOCK_STATS, report: MOCK_REPORT }), 1800);
}

function stopPlayback() {
  if (!sim) return;
  isPlaying = false;
  playPauseBtn.textContent = "▶ Play";
  playPauseBtn.classList.remove("active");
  sim.stop();
  if (timerInterval) clearInterval(timerInterval);
}

function resetPlayback() {
  stopPlayback();
  mockTime.textContent = "00:00";
  mountOverlay();
  createSimulator(scenarioSelect.value as ScenarioName);
}

function applyTheme() {
  const isDark = darkToggle.checked;
  document.body.classList.toggle("light", !isDark);
  if (host) {
    if (isDark) {
      host.host.classList.add("dark");
    } else {
      host.host.classList.remove("dark");
    }
  }
}

playPauseBtn.addEventListener("click", () => {
  if (isPlaying) {
    pausePlayback();
  } else {
    if (!sim) {
      createSimulator(scenarioSelect.value as ScenarioName);
    }
    startPlayback();
  }
});

resetBtn.addEventListener("click", () => resetPlayback());

scenarioSelect.addEventListener("change", () => {
  resetPlayback();
});

speedSelect.addEventListener("change", () => {
  const speed = parseInt(speedSelect.value, 10);
  sim?.setSpeed(speed);
});

darkToggle.addEventListener("change", () => applyTheme());

mountOverlay();
createSimulator("normalFlow");
