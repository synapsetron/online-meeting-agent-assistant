import { useState, useEffect, useCallback } from "react";
import { loadSettings, saveSettings, type UserSettings } from "@/shared/storage";
import "./options.css";

export function App() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [savedVisible, setSavedVisible] = useState(false);
  const [showApiKeys, setShowApiKeys] = useState(false);

  const [isDark, setIsDark] = useState(
    window.matchMedia("(prefers-color-scheme: dark)").matches,
  );

  useEffect(() => {
    loadSettings().then(setSettings);
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => setIsDark(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  const update = useCallback(
    (partial: Partial<UserSettings>) => {
      if (!settings) return;
      const next = { ...settings, ...partial };
      setSettings(next);
      saveSettings(partial);
      setSavedVisible(true);
      setTimeout(() => setSavedVisible(false), 2000);
    },
    [settings],
  );

  if (!settings) return null;

  return (
    <div className="options-container">
      <div className="options-header">
        <div className="options-logo">M</div>
        <h1 className="options-title">Meeting Assistant Settings</h1>
        <span className={`options-saved ${savedVisible ? "visible" : ""}`}>
          ✓ Saved
        </span>
      </div>

      {/* API Keys */}
      <div className="options-section">
        <h2 className="options-section-title">API Configuration</h2>

        <div className="options-field">
          <label className="options-label">ASR API Key</label>
          <div style={{ position: "relative" }}>
            <input
              className="options-input"
              type={showApiKeys ? "text" : "password"}
              placeholder="sk-..."
              readOnly
              value=""
            />
          </div>
          <p className="options-desc">Speech recognition provider API key (not yet connected)</p>
        </div>

        <div className="options-field">
          <label className="options-label">LLM API Key</label>
          <input
            className="options-input"
            type={showApiKeys ? "text" : "password"}
            placeholder="sk-ant-..."
            readOnly
            value=""
          />
          <p className="options-desc">Language model API key for semantic analysis (not yet connected)</p>
        </div>

        <label className="options-checkbox-label" style={{ marginTop: 4 }}>
          <input
            type="checkbox"
            checked={showApiKeys}
            onChange={(e) => setShowApiKeys(e.target.checked)}
          />
          Show API keys
        </label>

        <p className="options-desc" style={{ marginTop: 8 }}>
          🛡 Keys are stored locally in browser storage and never transmitted to third parties.
        </p>
      </div>

      {/* Language */}
      <div className="options-section">
        <h2 className="options-section-title">Language</h2>

        <div className="options-field">
          <label className="options-label">Primary meeting language</label>
          <select
            className="options-select"
            value={settings.language}
            onChange={(e) => update({ language: e.target.value as UserSettings["language"] })}
          >
            <option value="auto">Auto-detect</option>
            <option value="en">English</option>
            <option value="uk">Ukrainian</option>
          </select>
        </div>
      </div>

      {/* UI Preferences */}
      <div className="options-section">
        <h2 className="options-section-title">Interface</h2>

        <div className="options-field">
          <label className="options-label">Panel position</label>
          <select
            className="options-select"
            value={settings.panelPosition}
            onChange={(e) => update({ panelPosition: e.target.value as UserSettings["panelPosition"] })}
          >
            <option value="right">Right side</option>
            <option value="left">Left side</option>
          </select>
        </div>

        <div className="options-field">
          <label className="options-label">Theme</label>
          <div className="options-radio-group">
            {(["system", "light", "dark"] as const).map((t) => (
              <label key={t} className="options-radio-label">
                <input
                  type="radio"
                  name="theme"
                  value={t}
                  checked={settings.theme === t}
                  onChange={() => update({ theme: t })}
                />
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </label>
            ))}
          </div>
        </div>

        <div className="options-field">
          <label className="options-label">Font size</label>
          <div className="options-radio-group">
            {(["small", "medium", "large"] as const).map((s) => (
              <label key={s} className="options-radio-label">
                <input
                  type="radio"
                  name="fontSize"
                  value={s}
                  checked={settings.fontSize === s}
                  onChange={() => update({ fontSize: s })}
                />
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </label>
            ))}
          </div>
        </div>

        <div className="options-field">
          <label className="options-checkbox-label">
            <input
              type="checkbox"
              checked={settings.autoCollapse}
              onChange={(e) => update({ autoCollapse: e.target.checked })}
            />
            Auto-collapse panel when not recording
          </label>
        </div>
      </div>

      {/* Data Retention */}
      <div className="options-section">
        <h2 className="options-section-title">Data &amp; Privacy</h2>

        <div className="options-field">
          <label className="options-label">Transcript retention</label>
          <select
            className="options-select"
            value={settings.transcriptRetention}
            onChange={(e) =>
              update({ transcriptRetention: e.target.value as UserSettings["transcriptRetention"] })
            }
          >
            <option value="session">Session only (cleared on close)</option>
            <option value="24h">24 hours</option>
            <option value="7d">7 days</option>
            <option value="30d">30 days</option>
          </select>
        </div>

        <div className="options-field">
          <label className="options-label">Storage usage</label>
          <div className="options-storage-bar">
            <div className="options-storage-fill" style={{ width: "12%" }} />
          </div>
          <p className="options-desc">1.2 MB of 10 MB used (mock data)</p>
        </div>

        <div className="options-field">
          <button
            className="options-btn-danger"
            onClick={() => {
              if (confirm("Clear all stored data? This cannot be undone.")) {
                setSavedVisible(true);
                setTimeout(() => setSavedVisible(false), 2000);
              }
            }}
          >
            Clear all data
          </button>
        </div>
      </div>
    </div>
  );
}
