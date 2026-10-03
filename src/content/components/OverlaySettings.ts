import { el } from "../utils/dom";
import { isExtensionContext } from "@/shared/storage";
import { DEFAULT_WS_URL, DEFAULT_SPEECH_LANGUAGE } from "@/shared/constants";

const LANGUAGES = [
  { value: "uk-UA", label: "Українська" },
  { value: "en-US", label: "English (US)" },
  { value: "en-GB", label: "English (UK)" },
  { value: "de-DE", label: "Deutsch" },
  { value: "fr-FR", label: "Français" },
  { value: "pl-PL", label: "Polski" },
];

export class OverlaySettings {
  readonly root: HTMLElement;
  private backendInput!: HTMLInputElement;
  private languageSelect!: HTMLSelectElement;
  private apiKeyInput!: HTMLInputElement;
  private toggleBtn!: HTMLButtonElement;
  private savedLabel!: HTMLElement;
  private showKey = false;

  constructor(private onClose: () => void) {
    this.root = this.build();
    this.root.style.display = "none";
    this.loadValues();
  }

  private build(): HTMLElement {
    const header = el("div", { className: "ma-settings-header" }, [
      el("span", { className: "ma-settings-title", textContent: "Settings" }),
    ]);
    this.savedLabel = el("span", { className: "ma-settings-saved" });
    const closeBtn = el("button", {
      className: "ma-btn-icon",
      "aria-label": "Close settings",
      textContent: "✕",
    });
    closeBtn.addEventListener("click", () => this.hide());
    const headerRight = el("div", { className: "ma-settings-header-right" }, [
      this.savedLabel,
      closeBtn,
    ]);
    header.appendChild(headerRight);

    // Backend URL
    const urlLabel = el("label", { className: "ma-settings-label", textContent: "Backend URL" });
    this.backendInput = el("input", {
      className: "ma-settings-input",
      type: "url",
    }) as HTMLInputElement;
    this.backendInput.placeholder = DEFAULT_WS_URL;
    this.backendInput.addEventListener("change", () => this.saveValue("backendUrl", this.backendInput.value));

    // Language
    const langLabel = el("label", { className: "ma-settings-label", textContent: "Recognition language" });
    this.languageSelect = el("select", { className: "ma-settings-select" }) as HTMLSelectElement;
    for (const lang of LANGUAGES) {
      const opt = el("option", { value: lang.value, textContent: lang.label }) as HTMLOptionElement;
      this.languageSelect.appendChild(opt);
    }
    this.languageSelect.addEventListener("change", () => this.saveValue("speechLanguage", this.languageSelect.value));

    // API Key
    const keyLabel = el("label", { className: "ma-settings-label", textContent: "Anthropic API Key" });
    const keyRow = el("div", { className: "ma-settings-key-row" });
    this.apiKeyInput = el("input", {
      className: "ma-settings-input ma-settings-key-input",
      type: "password",
    }) as HTMLInputElement;
    this.apiKeyInput.placeholder = "sk-ant-api03-...";
    this.apiKeyInput.spellcheck = false;
    this.apiKeyInput.autocomplete = "off";
    this.apiKeyInput.addEventListener("change", () => this.saveValue("anthropicApiKey", this.apiKeyInput.value));

    this.toggleBtn = el("button", {
      className: "ma-settings-key-toggle",
      textContent: "Show",
      type: "button",
    }) as HTMLButtonElement;
    this.toggleBtn.addEventListener("click", () => {
      this.showKey = !this.showKey;
      this.apiKeyInput.type = this.showKey ? "text" : "password";
      this.toggleBtn.textContent = this.showKey ? "Hide" : "Show";
    });

    keyRow.appendChild(this.apiKeyInput);
    keyRow.appendChild(this.toggleBtn);

    const keyHint = el("p", { className: "ma-settings-hint", textContent: "Required for AI-powered hints." });

    return el("div", { className: "ma-settings-panel" }, [
      header,
      urlLabel, this.backendInput,
      langLabel, this.languageSelect,
      keyLabel, keyRow, keyHint,
    ]);
  }

  private loadValues() {
    if (!isExtensionContext()) return;
    chrome.storage.local.get(["backendUrl", "speechLanguage", "anthropicApiKey"], (result) => {
      this.backendInput.value = (result.backendUrl as string) || DEFAULT_WS_URL;
      this.languageSelect.value = (result.speechLanguage as string) || DEFAULT_SPEECH_LANGUAGE;
      if (result.anthropicApiKey) {
        this.apiKeyInput.value = result.anthropicApiKey as string;
      }
    });
  }

  private saveValue(key: string, value: string) {
    if (isExtensionContext()) {
      chrome.storage.local.set({ [key]: value });
    }
    this.flash();
  }

  private flash() {
    this.savedLabel.textContent = "Saved";
    setTimeout(() => { this.savedLabel.textContent = ""; }, 1500);
  }

  show() {
    this.root.style.display = "";
    this.loadValues();
  }

  hide() {
    this.root.style.display = "none";
    this.onClose();
  }

  get isVisible(): boolean {
    return this.root.style.display !== "none";
  }

  destroy() {
    // no timers to clean
  }
}
