import { el } from "../utils/dom";

export class CollapsibleSection {
  readonly root: HTMLElement;
  readonly content: HTMLElement;
  private chevron: HTMLElement;
  private badge: HTMLElement;
  private isOpen = true;

  constructor(title: string, ariaLabel: string, extraHeaderChildren?: Node[]) {
    this.chevron = el("span", { className: "ma-section-chevron open", textContent: "▸" });
    this.badge = el("span", { className: "ma-section-badge", textContent: "0" });

    const titleEl = el("span", { className: "ma-section-title", textContent: title });

    const headerChildren: Node[] = [
      this.chevron,
      ...(extraHeaderChildren ? [titleEl, ...extraHeaderChildren] : [titleEl]),
      this.badge,
    ];

    const header = el("div", {
      className: "ma-section-header",
      role: "button",
      tabindex: "0",
      "aria-expanded": "true",
      "aria-label": ariaLabel,
    }, headerChildren);

    header.addEventListener("click", () => this.toggle());
    header.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        this.toggle();
      }
    });

    this.content = el("div", { className: "ma-section-content" });
    this.root = el("div", { className: "ma-section" }, [header, this.content]);
  }

  private toggle() {
    this.isOpen = !this.isOpen;
    this.chevron.className = `ma-section-chevron${this.isOpen ? " open" : ""}`;
    this.content.className = `ma-section-content${this.isOpen ? "" : " closed"}`;
    const header = this.root.querySelector(".ma-section-header");
    header?.setAttribute("aria-expanded", String(this.isOpen));
  }

  setBadge(text: string) {
    this.badge.textContent = text;
  }
}
