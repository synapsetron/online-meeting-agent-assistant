import { ShadowHost } from "./shadow-host";
import { OverlayContainer } from "./components/OverlayContainer";
import { ThemeManager } from "./components/ThemeManager";
import { MeetingSimulator } from "@/mock/meeting-simulator";
import { SCENARIOS } from "@/mock/scenarios";
import { CaptureState } from "@/types/meeting";

function init() {
  const host = new ShadowHost("open");

  const overlay = new OverlayContainer({
    onDismissHint: (hintId) => {
      console.log("[Meeting Assistant] Hint dismissed:", hintId);
    },
    onStopCapture: () => {
      sim.pause();
      overlay.setCaptureState(CaptureState.Stopped);
    },
  });

  host.mount(overlay.root);

  const theme = new ThemeManager(host.host);
  theme.init();

  const scenario = SCENARIOS.normalFlow;
  const sim = new MeetingSimulator(scenario);

  sim.on("speakers", (speakers) => overlay.setSpeakers(speakers));
  sim.on("agenda", (state) => overlay.updateAgenda(state));
  sim.on("transcript", (segment) => overlay.addTranscript(segment));
  sim.on("hint", (hint) => overlay.addHint(hint));
  sim.on("captureState", (state) => overlay.setCaptureState(state));

  sim.start();

  window.addEventListener("beforeunload", () => {
    sim.stop();
    overlay.destroy();
    theme.destroy();
    host.destroy();
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
