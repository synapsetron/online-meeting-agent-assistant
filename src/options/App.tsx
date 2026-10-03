import { useState, useEffect, useCallback } from "react";
import { loadSettings, saveSettings, isExtensionContext, type UserSettings } from "@/shared/storage";
import { DEFAULT_WS_URL, DEFAULT_SPEECH_LANGUAGE } from "@/shared/constants";
import { useTheme } from "@/shared/hooks/useTheme";
import "./options.css";

const SPEECH_LANGUAGES = [
  { value: "uk-UA", label: "Ukrainian (Українська)" },
  { value: "en-US", label: "English (US)" },
  { value: "en-GB", label: "English (UK)" },
  { value: "de-DE", label: "German (Deutsch)" },
  { value: "fr-FR", label: "French (Français)" },
  { value: "pl-PL", label: "Polish (Polski)" },
] as const;

export function App() {
  useTheme();

  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [savedVisible, setSavedVisible] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [backendUrl, setBackendUrl] = useState(DEFAULT_WS_URL);
  const [speechLanguage, setSpeechLanguage] = useState(DEFAULT_SPEECH_LANGUAGE);
  const [apiKey, setApiKey] = useState("");

  useEffect(() => {
    loadSettings().then(setSettings);
    if (isExtensionContext()) {
      chrome.storage.local.get(["backendUrl", "speechLanguage", "anthropicApiKey"]).then((result) => {
        if (result.backendUrl) setBackendUrl(result.backendUrl as string);
        if (result.speechLanguage) setSpeechLanguage(result.speechLanguage as string);
        if (result.anthropicApiKey) setApiKey(result.anthropicApiKey as string);
      });
    }
  }, []);

  const showSaved = useCallback(() => {
    setSavedVisible(true);
    setTimeout(() => setSavedVisible(false), 2000);
  }, []);

  const update = useCallback(
    (partial: Partial<UserSettings>) => {
      if (!settings) return;
      const next = { ...settings, ...partial };
      setSettings(next);
      saveSettings(partial);
      showSaved();
    },
    [settings, showSaved],
  );

  const handleBackendUrlChange = useCallback(
    (url: string) => {
      setBackendUrl(url);
      if (isExtensionContext()) {
        chrome.storage.local.set({ backendUrl: url });
      }
      showSaved();
    },
    [showSaved],
  );

  const handleSpeechLanguageChange = useCallback(
    (lang: string) => {
      setSpeechLanguage(lang);
      if (isExtensionContext()) {
        chrome.storage.local.set({ speechLanguage: lang });
      }
      showSaved();
    },
    [showSaved],
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

      <div className="options-section">
        <h2 className="options-section-title">Backend Connection</h2>
        <div className="options-field">
          <label className="options-label">WebSocket URL</label>
          <input
            className="options-input"
            type="url"
            placeholder={DEFAULT_WS_URL}
            value={backendUrl}
            onChange={(e) => handleBackendUrlChange(e.target.value)}
          />
          <p className="options-desc">
            The WebSocket endpoint of the meeting assistant backend server.
            Default: {DEFAULT_WS_URL}
          </p>
        </div>
      </div>

      <div className="options-section">
        <h2 className="options-section-title">Speech Recognition</h2>
        <div className="options-field">
          <label className="options-label">Recognition language</label>
          <select
            className="options-select"
            value={speechLanguage}
            onChange={(e) => handleSpeechLanguageChange(e.target.value)}
          >
            {SPEECH_LANGUAGES.map((lang) => (
              <option key={lang.value} value={lang.value}>
                {lang.label}
              </option>
            ))}
          </select>
          <p className="options-desc">
            Language used for speech recognition via the Web Speech API.
            Choose the language spoken in your meetings.
          </p>
        </div>
      </div>

      <div className="options-section">
        <h2 className="options-section-title">API Configuration</h2>
        <div className="options-field">
          <label className="options-label">Anthropic API Key</label>
          <div className="options-api-key-row">
            <input
              className="options-input options-api-key-input"
              type={showApiKey ? "text" : "password"}
              placeholder="sk-ant-api03-..."
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                if (isExtensionContext()) {
                  chrome.storage.local.set({ anthropicApiKey: e.target.value });
                }
                showSaved();
              }}
              spellCheck={false}
              autoComplete="off"
            />
            <button
              className="options-api-key-toggle"
              onClick={() => setShowApiKey(!showApiKey)}
              type="button"
            >
              {showApiKey ? "Hide" : "Show"}
            </button>
          </div>
          <p className="options-desc">
            Required for AI-powered hints and meeting analysis.
            Sent to the backend server at connection time.
            {apiKey ? " Key is stored locally." : ""}
          </p>
        </div>
      </div>

      <div className="options-section">
        <h2 className="options-section-title">Interface Language</h2>
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
                showSaved();
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
