import { detectTheme, onThemeChange, type Theme } from "@/shared/theme";

export class ThemeManager {
  private host: HTMLElement;
  private cleanup: (() => void) | null = null;

  constructor(host: HTMLElement) {
    this.host = host;
  }

  async init() {
    const theme = await detectTheme();
    this.apply(theme);
    this.cleanup = onThemeChange((t) => this.apply(t));
  }

  private apply(theme: Theme) {
    if (theme === "dark") {
      this.host.classList.add("dark");
    } else {
      this.host.classList.remove("dark");
    }
  }

  destroy() {
    this.cleanup?.();
  }
}
