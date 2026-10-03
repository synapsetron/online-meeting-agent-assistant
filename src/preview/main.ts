import { ShadowHost } from "../content/shadow-host";
import { OverlayContainer } from "../content/components/OverlayContainer";
import { ThemeManager } from "../content/components/ThemeManager";
import { MeetingSimulator } from "../mock/meeting-simulator";
import { SCENARIOS, type ScenarioName } from "../mock/scenarios";
import { CaptureState } from "../types/meeting";

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
    onStopCapture: () => stopPlayback(),
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
