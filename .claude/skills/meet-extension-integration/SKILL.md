---
name: meet-extension-integration
description: Design a Chrome extension and unobtrusive assistant UI for Google Meet. Use for capture feasibility, permissions, extension architecture, consent, or UI prototypes.
---

# Google Meet and browser extension integration

Do not assume Google Meet REST APIs expose a live audio/video stream. Treat live tab capture and Meet REST artifacts as separate paths: Chrome `tabCapture` can provide tab media after a user-initiated extension action; Meet REST resources include conference records and artifacts such as transcripts, generally available after a conference. Verify current documentation before relying on a capability.

For Chrome Manifest V3, design around the service worker lifecycle, user-initiated action, and only the necessary host/API permissions. Consider optional permissions where appropriate. Explain which data is captured and transmitted. Test whether captured audio remains audible to the user and route it back when required. Do not promise isolated participant tracks unless the chosen source actually provides them.

Keep any Meet-page integration isolated: the page DOM is not a stable public API. Make the overlay accessible, compact, dismissible, keyboard-operable, and removable when capture stops. Handle tab navigation/reload/close, revoked permissions, network errors, and capture termination.

Capture must be explicit and visible, with consent, a clear stop control, minimal retention, and safe test data. Never embed provider keys in extension code; use an authenticated server-side boundary. Avoid broad permissions and hidden recording.

References: [Chrome `tabCapture`](https://developer.chrome.com/docs/extensions/reference/api/tabCapture), [Chrome permission declarations](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions), [Meet API overview](https://developers.google.com/workspace/meet/api/guides/overview), and [Meet artifacts](https://developers.google.com/workspace/meet/api/guides/artifacts).
