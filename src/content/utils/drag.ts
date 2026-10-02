export interface DragState {
  startX: number;
  startY: number;
  startLeft: number;
  startTop: number;
}

export function makeDraggable(
  handle: HTMLElement,
  target: HTMLElement,
  onDragStart?: () => void,
  onDragEnd?: () => void,
): () => void {
  let state: DragState | null = null;

  function onPointerDown(e: PointerEvent) {
    if ((e.target as HTMLElement).closest("button")) return;
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);

    const rect = target.getBoundingClientRect();
    state = {
      startX: e.clientX,
      startY: e.clientY,
      startLeft: rect.left,
      startTop: rect.top,
    };
    onDragStart?.();
  }

  function onPointerMove(e: PointerEvent) {
    if (!state) return;
    const dx = e.clientX - state.startX;
    const dy = e.clientY - state.startY;

    const newLeft = Math.max(
      0,
      Math.min(window.innerWidth - 100, state.startLeft + dx),
    );
    const newTop = Math.max(
      0,
      Math.min(window.innerHeight - 50, state.startTop + dy),
    );

    target.style.left = `${newLeft}px`;
    target.style.top = `${newTop}px`;
    target.style.right = "auto";
  }

  function onPointerUp() {
    state = null;
    onDragEnd?.();
  }

  handle.addEventListener("pointerdown", onPointerDown);
  handle.addEventListener("pointermove", onPointerMove);
  handle.addEventListener("pointerup", onPointerUp);

  return () => {
    handle.removeEventListener("pointerdown", onPointerDown);
    handle.removeEventListener("pointermove", onPointerMove);
    handle.removeEventListener("pointerup", onPointerUp);
  };
}

export function makeResizable(
  handle: HTMLElement,
  target: HTMLElement,
  direction: "horizontal" | "vertical",
  minSize: number,
  maxSize: number,
): () => void {
  let startPos = 0;
  let startSize = 0;

  function onPointerDown(e: PointerEvent) {
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    startPos = direction === "horizontal" ? e.clientX : e.clientY;
    startSize =
      direction === "horizontal"
        ? target.getBoundingClientRect().width
        : target.getBoundingClientRect().height;
  }

  function onPointerMove(e: PointerEvent) {
    if (!startSize) return;
    const diff =
      direction === "horizontal"
        ? startPos - e.clientX
        : e.clientY - startPos;
    const newSize = Math.max(minSize, Math.min(maxSize, startSize + diff));

    if (direction === "horizontal") {
      target.style.width = `${newSize}px`;
    } else {
      target.style.maxHeight = `${newSize}px`;
    }
  }

  function onPointerUp() {
    startSize = 0;
  }

  handle.addEventListener("pointerdown", onPointerDown);
  handle.addEventListener("pointermove", onPointerMove);
  handle.addEventListener("pointerup", onPointerUp);

  return () => {
    handle.removeEventListener("pointerdown", onPointerDown);
    handle.removeEventListener("pointermove", onPointerMove);
    handle.removeEventListener("pointerup", onPointerUp);
  };
}
