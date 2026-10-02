export interface UserSettings {
  panelPosition: "right" | "left";
  theme: "system" | "light" | "dark";
  fontSize: "small" | "medium" | "large";
  autoCollapse: boolean;
  language: "en" | "uk" | "auto";
  transcriptRetention: "session" | "24h" | "7d" | "30d";
}

export const DEFAULT_SETTINGS: UserSettings = {
  panelPosition: "right",
  theme: "system",
  fontSize: "medium",
  autoCollapse: false,
  language: "auto",
  transcriptRetention: "session",
};

export function isExtensionContext(): boolean {
  return (
    typeof chrome !== "undefined" &&
    typeof chrome.storage !== "undefined" &&
    typeof chrome.storage.local !== "undefined"
  );
}

const memoryStore: Record<string, unknown> = {};

export async function loadSettings(): Promise<UserSettings> {
  if (isExtensionContext()) {
    const result = await chrome.storage.local.get("settings");
    return { ...DEFAULT_SETTINGS, ...(result.settings as Partial<UserSettings>) };
  }
  const stored = memoryStore["settings"] as Partial<UserSettings> | undefined;
  return { ...DEFAULT_SETTINGS, ...stored };
}

export async function saveSettings(
  settings: Partial<UserSettings>,
): Promise<void> {
  const current = await loadSettings();
  const merged = { ...current, ...settings };
  if (isExtensionContext()) {
    await chrome.storage.local.set({ settings: merged });
  } else {
    memoryStore["settings"] = merged;
  }
}
