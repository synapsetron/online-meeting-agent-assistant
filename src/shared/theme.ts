import { loadSettings } from "./storage";

export type Theme = "light" | "dark";

export async function detectTheme(): Promise<Theme> {
  const settings = await loadSettings();
  if (settings.theme === "light") return "light";
  if (settings.theme === "dark") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function onThemeChange(callback: (theme: Theme) => void): () => void {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = () => {
    detectTheme().then(callback);
  };
  mq.addEventListener("change", handler);
  return () => mq.removeEventListener("change", handler);
}
