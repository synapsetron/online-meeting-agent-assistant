const MEETING_CODE_PATTERN = /^\/([a-z]{3}-[a-z]{4}-[a-z]{3})$/;

export function getMeetingCode(): string | null {
  try {
    const url = new URL(window.location.href);
    if (url.hostname !== "meet.google.com") {
      return null;
    }
    const match = url.pathname.match(MEETING_CODE_PATTERN);
    return match ? match[1] : null;
  } catch {
    return null;
  }
}

export function isMeetCallActive(): boolean {
  // Must have a valid meeting code in the URL first
  if (!getMeetingCode()) {
    return false;
  }

  // Check for the call end button (red hang-up button) — a strong signal
  // Google Meet uses [data-call-ended] or specific aria labels
  const endCallButton = document.querySelector(
    '[aria-label*="Leave" i], [aria-label*="leave" i], ' +
    '[aria-label*="Залишити" i], [aria-label*="залишити" i], ' +
    '[aria-label*="Покинуть" i], [aria-label*="покинуть" i], ' +
    '[data-tooltip*="Leave" i], [data-tooltip*="leave" i]'
  );

  // Check for mute/camera control buttons
  const controlButtons = document.querySelector(
    '[aria-label*="microphone" i], [aria-label*="camera" i], ' +
    '[aria-label*="мікрофон" i], [aria-label*="камер" i], ' +
    '[aria-label*="Микрофон" i], [aria-label*="микрофон" i]'
  );

  // If we find both end-call and control buttons, call is active
  if (endCallButton && controlButtons) {
    return true;
  }

  // Fallback: check for participant video elements
  // Google Meet renders video in specific containers
  const hasVideoElements = document.querySelectorAll("video").length > 0;
  const hasMeetUI = document.querySelector('[data-meeting-code], [data-resolution-cap]') !== null;

  return hasVideoElements || hasMeetUI;
}

export function observeCallState(
  onCallStateChange: (active: boolean) => void,
): () => void {
  let wasActive = isMeetCallActive();

  // Notify initial state
  onCallStateChange(wasActive);

  const observer = new MutationObserver(() => {
    const isActive = isMeetCallActive();
    if (isActive !== wasActive) {
      wasActive = isActive;
      onCallStateChange(isActive);
    }
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["aria-label", "data-tooltip"],
  });

  return () => observer.disconnect();
}
