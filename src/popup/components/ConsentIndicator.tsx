import { useState } from "react";

export function ConsentIndicator() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div style={{ padding: "10px 16px 14px" }}>
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          border: "none",
          background: "transparent",
          cursor: "pointer",
          padding: 0,
          fontFamily: "inherit",
          fontSize: 12,
          color: "var(--popup-text-tertiary)",
        }}
      >
        <span style={{ fontSize: 14 }}>🛡</span>
        <span>Privacy: local processing only</span>
        <span
          style={{
            fontSize: 10,
            transition: "transform 150ms",
            transform: expanded ? "rotate(90deg)" : "none",
          }}
        >
          ▸
        </span>
      </button>
      {expanded && (
        <p
          style={{
            fontSize: 11,
            color: "var(--popup-text-tertiary)",
            marginTop: 6,
            lineHeight: 1.5,
            paddingLeft: 20,
          }}
        >
          Audio is captured from the active tab and processed locally. No audio
          data is stored or transmitted to external servers. Transcript text is
          kept only for the duration of the session and can be cleared at any
          time from Settings.
        </p>
      )}
    </div>
  );
}
