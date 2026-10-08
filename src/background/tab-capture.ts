import { ensureOffscreenDocument, closeOffscreenDocument } from "./offscreen";
import type { SessionState } from "./session-state";

export async function startTabCapture(state: SessionState): Promise<boolean> {
  try {
    await ensureOffscreenDocument();
    const streamId = await chrome.tabCapture.getMediaStreamId({});

    await chrome.runtime.sendMessage({
      type: "START_TAB_CAPTURE",
      streamId,
    });

    state.tabCaptureActive = true;
    console.log("[ServiceWorker] Tab capture initiated");
    return true;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown tab capture error";
    console.warn("[ServiceWorker] Tab capture failed, microphone-only mode:", message);
    await closeOffscreenDocument().catch(() => {});
    state.tabCaptureActive = false;
    return false;
  }
}

export async function stopTabCapture(state: SessionState): Promise<void> {
  if (!state.tabCaptureActive) {
    return;
  }

  try {
    await chrome.runtime.sendMessage({ type: "STOP_TAB_CAPTURE" });
  } catch {
    // Offscreen document may already be closed
  }

  await closeOffscreenDocument().catch(() => {});
  state.tabCaptureActive = false;
  console.log("[ServiceWorker] Tab capture stopped");
}
