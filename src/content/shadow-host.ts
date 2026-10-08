import styles from "./styles.css?inline";

const HOST_ID = "meeting-assistant-host";

export class ShadowHost {
  readonly host: HTMLElement;
  readonly shadow: ShadowRoot;

  constructor(mode: "open" | "closed" = "open") {
    const existing = document.getElementById(HOST_ID);
    if (existing) existing.remove();

    this.host = document.createElement("div");
    this.host.id = HOST_ID;
    this.shadow = this.host.attachShadow({ mode });

    const styleSheet = new CSSStyleSheet();
    styleSheet.replaceSync(styles);
    this.shadow.adoptedStyleSheets = [styleSheet];

    document.body.appendChild(this.host);
  }

  mount(element: HTMLElement) {
    this.shadow.appendChild(element);
  }

  destroy() {
    this.host.remove();
  }
}
