import { useState, useEffect, useCallback } from "react";
import { DEFAULT_WS_URL, DEFAULT_SPEECH_LANGUAGE } from "@/shared/constants";
import { isExtensionContext } from "@/shared/storage";

const SPEECH_LANGUAGES = [
  { value: "uk-UA", label: "Українська" },
  { value: "en-US", label: "English (US)" },
  { value: "en-GB", label: "English (UK)" },
  { value: "de-DE", label: "Deutsch" },
  { value: "fr-FR", label: "Français" },
  { value: "pl-PL", label: "Polski" },
] as const;

interface Props {
  onClose: () => void;
}

export function SettingsPanel({ onClose }: Props) {
  const [backendUrl, setBackendUrl] = useState(DEFAULT_WS_URL);
  const [speechLanguage, setSpeechLanguage] = useState(DEFAULT_SPEECH_LANGUAGE);
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");

  useEffect(() => {
    if (!isExtensionContext()) return;
    chrome.storage.local.get(["backendUrl", "speechLanguage", "anthropicApiKey"], (result) => {
      if (result.backendUrl) setBackendUrl(result.backendUrl as string);
      if (result.speechLanguage) setSpeechLanguage(result.speechLanguage as string);
      if (result.anthropicApiKey) setApiKey(result.anthropicApiKey as string);
    });
  }, []);

  const flash = useCallback((msg: string) => {
    setSavedMsg(msg);
    setTimeout(() => setSavedMsg(""), 1500);
  }, []);

  const handleBackendUrlChange = (url: string) => {
    setBackendUrl(url);
    if (isExtensionContext()) {
      chrome.storage.local.set({ backendUrl: url });
    }
    flash("Saved");
  };

  const handleLanguageChange = (lang: string) => {
    setSpeechLanguage(lang);
    if (isExtensionContext()) {
      chrome.storage.local.set({ speechLanguage: lang });
    }
    flash("Saved");
  };

  const handleApiKeyChange = (key: string) => {
    setApiKey(key);
    if (isExtensionContext()) {
      chrome.storage.local.set({ anthropicApiKey: key });
    }
    flash("Key saved");
  };

  const handleOpenFullSettings = () => {
    if (chrome.runtime?.openOptionsPage) {
      chrome.runtime.openOptionsPage();
    }
  };

  const maskedKey = apiKey
    ? apiKey.slice(0, 7) + "•".repeat(Math.min(apiKey.length - 7, 20))
    : "";

  return (
    <div className="settings-panel">
      <div className="settings-panel-header">
        <span className="settings-panel-title">Settings</span>
        <div className="settings-panel-header-right">
          {savedMsg && <span className="settings-saved-badge">{savedMsg}</span>}
          <button className="settings-panel-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
      </div>

      <div className="settings-group">
        <label className="settings-label">Backend URL</label>
        <input
          className="settings-input"
          type="url"
          value={backendUrl}
          onChange={(e) => handleBackendUrlChange(e.target.value)}
          placeholder={DEFAULT_WS_URL}
        />
      </div>

      <div className="settings-group">
        <label className="settings-label">Recognition language</label>
        <select
          className="settings-select"
          value={speechLanguage}
          onChange={(e) => handleLanguageChange(e.target.value)}
        >
          {SPEECH_LANGUAGES.map((lang) => (
            <option key={lang.value} value={lang.value}>
              {lang.label}
            </option>
          ))}
        </select>
      </div>

      <div className="settings-group">
        <label className="settings-label">Anthropic API Key</label>
        <div className="settings-api-key-row">
          <input
            className="settings-input settings-api-key-input"
            type={showApiKey ? "text" : "password"}
            value={showApiKey ? apiKey : maskedKey}
            onChange={(e) => handleApiKeyChange(e.target.value)}
            placeholder="sk-ant-api03-..."
            spellCheck={false}
            autoComplete="off"
          />
          <button
            className="settings-api-key-toggle"
            onClick={() => setShowApiKey(!showApiKey)}
            type="button"
            aria-label={showApiKey ? "Hide API key" : "Show API key"}
          >
            {showApiKey ? "Hide" : "Show"}
          </button>
        </div>
        <p className="settings-hint">
          {apiKey ? "Key stored locally in extension." : "Required for AI-powered hints."}
        </p>
      </div>

      <div className="settings-footer">
        <button className="settings-full-btn" onClick={handleOpenFullSettings}>
          All settings...
        </button>
      </div>
    </div>
  );
}
