import { useState } from "react";

export function ConsentIndicator() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="consent-section">
      <button className="consent-btn" onClick={() => setExpanded(!expanded)}>
        <span className="consent-icon">🛡</span>
        <span>Privacy: local processing only</span>
        <span className={`consent-chevron${expanded ? " expanded" : ""}`}>▸</span>
      </button>
      {expanded && (
        <p className="consent-details">
          Audio is captured from the active tab and processed locally. No audio
          data is stored or transmitted to external servers. Transcript text is
          kept only for the duration of the session and can be cleared at any
          time from Settings.
        </p>
      )}
    </div>
  );
}
