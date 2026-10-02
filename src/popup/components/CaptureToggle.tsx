import { CaptureState } from "@/types/meeting";

interface Props {
  captureState: CaptureState;
  onToggle: () => void;
}

export function CaptureToggle({ captureState, onToggle }: Props) {
  const isCapturing = captureState === CaptureState.Capturing;

  return (
    <div className="capture-section">
      <button
        className={`capture-btn${isCapturing ? " active" : ""}`}
        onClick={onToggle}
      >
        {isCapturing && <span className="capture-dot" />}
        {isCapturing ? "Stop capture" : "Start capture"}
      </button>
      <p className="capture-hint">
        {isCapturing
          ? "Transcript is being sent to backend for analysis."
          : "Connects to backend and starts speech recognition."}
      </p>
    </div>
  );
}
