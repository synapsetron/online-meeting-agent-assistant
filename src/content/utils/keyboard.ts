export function trapFocus(container: HTMLElement): () => void {
  function handler(e: KeyboardEvent) {
    if (e.key !== "Tab") return;

    const focusable = container.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  container.addEventListener("keydown", handler);
  return () => container.removeEventListener("keydown", handler);
}

export function onEscape(
  container: HTMLElement,
  callback: () => void,
): () => void {
  function handler(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.stopPropagation();
      callback();
    }
  }
  container.addEventListener("keydown", handler);
  return () => container.removeEventListener("keydown", handler);
}
