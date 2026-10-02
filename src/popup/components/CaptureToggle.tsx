import { CaptureState } from "@/types/meeting";

interface Props {
  captureState: CaptureState;
  onToggle: () => void;
}

export function CaptureToggle({ captureState, onToggle }: Props) {
  const isCapturing = captureState === CaptureState.Capturing;
  const isStopped = captureState === CaptureState.Stopped;

  return (
    <div style={{ padding: "12px 16px" }}>
      <button
        onClick={onToggle}
        disabled={isStopped}
        style={{
          width: "100%",
          padding: "10px 16px",
          border: "none",
          borderRadius: 10,
          cursor: isStopped ? "default" : "pointer",
          fontSize: 14,
          fontWeight: 600,
          fontFamily: "inherit",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
          transition: "background 150ms, transform 100ms",
          background: isCapturing
            ? "var(--popup-danger)"
            : isStopped
              ? "var(--popup-bg-tertiary)"
              : "var(--popup-accent)",
          color: isStopped ? "var(--popup-text-tertiary)" : "white",
          opacity: isStopped ? 0.6 : 1,
        }}
      >
        {isCapturing && (
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "white",
              animation: "pulse 1.5s ease-in-out infinite",
            }}
          />
        )}
        {isCapturing
          ? "Stop capture"
          : isStopped
            ? "Session ended"
            : "Start capture"}
      </button>
      {!isStopped && (
        <p
          style={{
            fontSize: 11,
            color: "var(--popup-text-tertiary)",
            textAlign: "center",
            marginTop: 6,
          }}
        >
          Audio from this tab will be processed locally.
        </p>
      )}
    </div>
  );
}
