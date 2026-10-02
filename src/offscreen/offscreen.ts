/**
 * Offscreen document for processing tab audio captured via chrome.tabCapture.
 *
 * In Manifest V3, service workers cannot access DOM or media APIs directly.
 * This offscreen document receives a stream ID from the service worker,
 * creates a MediaStream from it, and processes the audio.
 *
 * Currently logs that audio is being captured. Actual ASR integration
 * (feeding audio to a recognition engine) will be added in a later phase.
 */

import type {
  ServiceWorkerToOffscreen,
  OffscreenToServiceWorker,
} from "@/types/messages";

let audioContext: AudioContext | null = null;
let mediaStream: MediaStream | null = null;
let sourceNode: MediaStreamAudioSourceNode | null = null;
let analyserNode: AnalyserNode | null = null;

/**
 * Start capturing audio from the given stream ID.
 * The stream ID comes from chrome.tabCapture.getMediaStreamId() in the service worker.
 */
async function startCapture(streamId: string): Promise<void> {
  try {
    // Clean up any existing capture
    stopCapture();

    // Create MediaStream using the tab capture stream ID
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId,
        },
      } as MediaTrackConstraints,
      video: false,
    });

    // Set up AudioContext for processing
    audioContext = new AudioContext();
    sourceNode = audioContext.createMediaStreamSource(mediaStream);
    analyserNode = audioContext.createAnalyser();
    analyserNode.fftSize = 2048;

    sourceNode.connect(analyserNode);
    // Do not connect to destination to avoid feedback loops;
    // the tab audio is already playing in the browser.

    console.log("[Offscreen] Tab audio capture started, stream active");

    sendMessage({ type: "TAB_CAPTURE_STARTED" });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown capture error";
    console.error("[Offscreen] Failed to start tab capture:", message);
    sendMessage({ type: "TAB_CAPTURE_ERROR", error: message });
  }
}

/**
 * Stop capturing and release all audio resources.
 */
function stopCapture(): void {
  if (sourceNode) {
    sourceNode.disconnect();
    sourceNode = null;
  }

  if (analyserNode) {
    analyserNode.disconnect();
    analyserNode = null;
  }

  if (audioContext) {
    audioContext.close().catch(() => {
      // Ignore close errors during cleanup
    });
    audioContext = null;
  }

  if (mediaStream) {
    for (const track of mediaStream.getTracks()) {
      track.stop();
    }
    mediaStream = null;
  }

  console.log("[Offscreen] Tab audio capture stopped");
}

/**
 * Send a message to the service worker.
 */
function sendMessage(message: OffscreenToServiceWorker): void {
  chrome.runtime.sendMessage(message).catch((error) => {
    console.warn("[Offscreen] Failed to send message:", error);
  });
}

/**
 * Listen for messages from the service worker.
 */
chrome.runtime.onMessage.addListener(
  (message: ServiceWorkerToOffscreen, _sender, sendResponse) => {
    switch (message.type) {
      case "START_TAB_CAPTURE":
        startCapture(message.streamId)
          .then(() => sendResponse({ ok: true }))
          .catch(() => sendResponse({ ok: false }));
        return true; // Keep the message channel open for async response

      case "STOP_TAB_CAPTURE":
        stopCapture();
        sendMessage({ type: "TAB_CAPTURE_STOPPED" });
        sendResponse({ ok: true });
        break;
    }
  },
);
