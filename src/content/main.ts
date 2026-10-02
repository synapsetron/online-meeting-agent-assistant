import { ShadowHost } from "./shadow-host";
import { OverlayContainer } from "./components/OverlayContainer";
import { ThemeManager } from "./components/ThemeManager";
import { MeetingSimulator } from "@/mock/meeting-simulator";
import { SCENARIOS } from "@/mock/scenarios";
import { CaptureState } from "@/types/meeting";
import { getMeetingCode, observeCallState } from "@/shared/meet-detector";

/** Cleanup function for the call-state observer. */
let disconnectObserver: (() => void) | null = null;
let host: ShadowHost | null = null;
let overlay: OverlayContainer | null = null;
let theme: ThemeManager | null = null;
let sim: MeetingSimulator | null = null;

/**
 * Initialize the overlay UI and meeting simulator.
 * Only runs when a valid meeting code is detected in the URL.
 */
function initOverlay() {
  if (host) {
    // Already initialized
    return;
  }

  host = new ShadowHost("open");

  overlay = new OverlayContainer({
    onDismissHint: (hintId) => {
      console.log("[Meeting Assistant] Hint dismissed:", hintId);
    },
    onStopCapture: () => {
      sim?.pause();
      overlay?.setCaptureState(CaptureState.Stopped);
    },
  });

  host.mount(overlay.root);

  theme = new ThemeManager(host.host);
  theme.init();

  const scenario = SCENARIOS.normalFlow;
  sim = new MeetingSimulator(scenario);

  sim.on("speakers", (speakers) => overlay!.setSpeakers(speakers));
  sim.on("agenda", (state) => overlay!.updateAgenda(state));
  sim.on("transcript", (segment) => overlay!.addTranscript(segment));
  sim.on("hint", (hint) => overlay!.addHint(hint));
  sim.on("captureState", (state) => overlay!.setCaptureState(state));

  sim.start();

  console.log("[Meeting Assistant] Overlay initialized for meeting");
}

/**
 * Tear down the overlay and release all resources.
 */
function destroyOverlay() {
  sim?.stop();
  sim = null;

  overlay?.destroy();
  overlay = null;

  theme?.destroy();
  theme = null;

  host?.destroy();
  host = null;

  console.log("[Meeting Assistant] Overlay destroyed");
}

function init() {
  const meetingCode = getMeetingCode();

  if (!meetingCode) {
    console.log("[Meeting Assistant] Not a meeting page, overlay will not load");
    return;
  }

  console.log("[Meeting Assistant] Meeting page detected, code:", meetingCode);

  // Notify the service worker that the content script is ready
  chrome.runtime.sendMessage({ type: "CONTENT_READY" }).catch(() => {
    // Service worker may not be ready yet; non-fatal
  });

  // Observe call state via MutationObserver to detect join/leave
  disconnectObserver = observeCallState((active) => {
    if (active) {
      console.log("[Meeting Assistant] Call is active, showing overlay");
      initOverlay();
    } else {
      console.log("[Meeting Assistant] Call is not active, hiding overlay");
      destroyOverlay();
    }
  });
}

// Clean up on page unload
window.addEventListener("beforeunload", () => {
  disconnectObserver?.();
  destroyOverlay();
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
