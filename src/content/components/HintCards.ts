import type { Hint } from "@/types/hint";
import { HintType } from "@/types/hint";
import type { AgendaItem } from "@/types/agenda";
import { el } from "../utils/dom";
import { MAX_VISIBLE_HINTS } from "@/shared/constants";

const TYPE_ICONS: Record<HintType, string> = {
  [HintType.AgendaSuggestion]: "💡",
  [HintType.TopicDrift]: "🧭",
  [HintType.TimeWarning]: "⏰",
  [HintType.MissedItem]: "🚩",
  [HintType.Summary]: "📋",
};

const TYPE_LABELS: Record<HintType, string> = {
  [HintType.AgendaSuggestion]: "Suggestion",
  [HintType.TopicDrift]: "Topic drift",
  [HintType.TimeWarning]: "Time warning",
  [HintType.MissedItem]: "Missed item",
  [HintType.Summary]: "Summary",
};

const TYPE_CSS: Record<HintType, string> = {
  [HintType.AgendaSuggestion]: "",
  [HintType.TopicDrift]: "drift",
  [HintType.TimeWarning]: "time_warning",
  [HintType.MissedItem]: "missed_item",
  [HintType.Summary]: "summary",
};

export class HintCards {
  readonly root: HTMLElement;
  private section: HTMLElement;
  private sectionContent: HTMLElement;
  private list: HTMLElement;
  private badge: HTMLElement;
  private chevron: HTMLElement;
  private isOpen = true;
  private hints: Hint[] = [];
  private agendaItems: Map<string, AgendaItem> = new Map();
  private onDismiss: ((hintId: string) => void) | null = null;

  constructor(onDismiss?: (hintId: string) => void) {
    this.onDismiss = onDismiss ?? null;

    this.chevron = el("span", { className: "ma-section-chevron open", textContent: "▸" });
    this.badge = el("span", { className: "ma-section-badge", textContent: "0" });

    const header = el("div", {
      className: "ma-section-header",
      role: "button",
      tabindex: "0",
      "aria-expanded": "true",
      "aria-label": "Suggestions section",
    }, [
      this.chevron,
      el("span", { className: "ma-section-title", textContent: "Suggestions" }),
      this.badge,
    ]);

    header.addEventListener("click", () => this.toggle());
    header.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        this.toggle();
      }
    });

    this.list = el("div", { className: "ma-hints-list" });
    this.list.innerHTML = `<div class="ma-hints-empty">No suggestions yet</div>`;

    this.sectionContent = el("div", { className: "ma-section-content" }, [this.list]);
    this.section = el("div", { className: "ma-section" }, [header, this.sectionContent]);
    this.root = this.section;
  }

  private toggle() {
    this.isOpen = !this.isOpen;
    this.chevron.className = `ma-section-chevron${this.isOpen ? " open" : ""}`;
    this.sectionContent.className = `ma-section-content${this.isOpen ? "" : " closed"}`;
  }

  setAgendaItems(items: AgendaItem[]) {
    this.agendaItems.clear();
    for (const item of items) {
      this.agendaItems.set(item.id, item);
    }
  }

  addHint(hint: Hint) {
    if (this.hints.some((h) => h.id === hint.id)) return;

    this.hints.unshift(hint);
    const visible = this.hints.filter((h) => !h.dismissed);

    if (visible.length === 1) {
      this.list.innerHTML = "";
    }

    const card = this.createHintCard(hint);
    this.list.insertBefore(card, this.list.firstChild);

    while (this.list.children.length > MAX_VISIBLE_HINTS) {
      this.list.lastChild?.remove();
    }

    this.updateBadge();
  }

  private dismissHint(hintId: string) {
    const card = this.list.querySelector(`[data-hint-id="${hintId}"]`) as HTMLElement | null;
    if (card) {
      card.classList.add("dismissing");
      setTimeout(() => {
        card.remove();
        const h = this.hints.find((h) => h.id === hintId);
        if (h) h.dismissed = true;
        this.updateBadge();
        if (this.list.children.length === 0) {
          this.list.innerHTML = `<div class="ma-hints-empty">No suggestions yet</div>`;
        }
      }, 200);
    }
    this.onDismiss?.(hintId);
  }

  private updateBadge() {
    const count = this.hints.filter((h) => !h.dismissed).length;
    this.badge.textContent = String(count);
  }

  private createHintCard(hint: Hint): HTMLElement {
    const typeClass = TYPE_CSS[hint.type];
    const icon = el("span", {
      className: "ma-hint-type-icon",
      textContent: TYPE_ICONS[hint.type],
    });
    const label = el("span", {
      className: "ma-hint-type-label",
      textContent: TYPE_LABELS[hint.type],
    });
    const dismissBtn = el("button", {
      className: "ma-hint-dismiss",
      textContent: "✕",
      "aria-label": "Dismiss suggestion",
    });
    dismissBtn.addEventListener("click", () => this.dismissHint(hint.id));

    const header = el("div", { className: "ma-hint-header" }, [icon, label, dismissBtn]);
    const message = el("div", { className: "ma-hint-message", textContent: hint.message });

    const confLevel =
      hint.confidence >= 0.8 ? "high" : hint.confidence >= 0.5 ? "medium" : "low";
    const confFill = el("div", {
      className: `ma-hint-confidence-fill ${confLevel}`,
    });
    confFill.style.width = `${Math.round(hint.confidence * 100)}%`;
    const confBar = el("div", { className: "ma-hint-confidence-bar" }, [confFill]);
    const confLabel = el("span", {
      textContent: `${Math.round(hint.confidence * 100)}%`,
    });
    const confidence = el("div", { className: "ma-hint-confidence" }, [confBar, confLabel]);

    const agendaItem = this.agendaItems.get(hint.agendaItemId);
    const agendaTag = agendaItem
      ? el("span", { className: "ma-hint-tag", textContent: agendaItem.title })
      : null;

    const footer = el("div", { className: "ma-hint-footer" }, [
      confidence,
      ...(agendaTag ? [agendaTag] : []),
    ]);

    const children: HTMLElement[] = [header, message, footer];

    if (hint.uncertainty) {
      const uncertainty = el("div", {
        className: "ma-hint-evidence",
        textContent: hint.uncertainty,
      });
      children.push(uncertainty);
    }

    const card = el("div", {
      className: `ma-hint-card ${typeClass}`,
      "data-hint-id": hint.id,
      role: "article",
      "aria-label": `${TYPE_LABELS[hint.type]}: ${hint.message}`,
    }, children);

    return card;
  }

  destroy() {
    this.hints = [];
  }
}
