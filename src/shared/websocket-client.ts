/**
 * WebSocket client for communicating with the meeting assistant backend.
 * Manages connection lifecycle, auto-reconnect with exponential backoff,
 * and type-safe message handling.
 */

import { DEFAULT_WS_URL } from "./constants";

export type ConnectionState = "disconnected" | "connecting" | "connected" | "reconnecting";

export type MessageCallback = (message: unknown) => void;

export interface WebSocketClientOptions {
  url?: string;
  maxReconnectDelay?: number;
  initialReconnectDelay?: number;
}

const DEFAULT_INITIAL_RECONNECT_DELAY = 1000;
const DEFAULT_MAX_RECONNECT_DELAY = 30000;

export class WebSocketClient {
  private url: string;
  private ws: WebSocket | null = null;
  private state: ConnectionState = "disconnected";
  private messageCallbacks: Set<MessageCallback> = new Set();
  private stateCallbacks: Set<(state: ConnectionState) => void> = new Set();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay: number;
  private initialReconnectDelay: number;
  private maxReconnectDelay: number;
  private shouldReconnect = false;
  private connectMessage: unknown = null;

  constructor(options?: WebSocketClientOptions) {
    this.url = options?.url ?? DEFAULT_WS_URL;
    this.initialReconnectDelay = options?.initialReconnectDelay ?? DEFAULT_INITIAL_RECONNECT_DELAY;
    this.maxReconnectDelay = options?.maxReconnectDelay ?? DEFAULT_MAX_RECONNECT_DELAY;
    this.reconnectDelay = this.initialReconnectDelay;
  }

  getState(): ConnectionState {
    return this.state;
  }

  private setState(state: ConnectionState): void {
    this.state = state;
    for (const cb of this.stateCallbacks) {
      try {
        cb(state);
      } catch (err) {
        console.error("[WebSocketClient] State callback error:", err);
      }
    }
  }

  connect(connectMessage: unknown): void {
    this.connectMessage = connectMessage;
    this.shouldReconnect = true;
    this.reconnectDelay = this.initialReconnectDelay;
    this.doConnect();
  }

  private doConnect(): void {
    this.cleanup();

    this.setState(this.state === "disconnected" ? "connecting" : "reconnecting");

    try {
      this.ws = new WebSocket(this.url);
    } catch (err) {
      console.error("[WebSocketClient] Failed to create WebSocket:", err);
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      console.log("[WebSocketClient] Connected to", this.url);
      this.setState("connected");
      this.reconnectDelay = this.initialReconnectDelay;

      if (this.connectMessage) {
        this.sendRaw(this.connectMessage);
      }
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data as string);
        for (const cb of this.messageCallbacks) {
          try {
            cb(data);
          } catch (err) {
            console.error("[WebSocketClient] Message callback error:", err);
          }
        }
      } catch (err) {
        console.error("[WebSocketClient] Failed to parse message:", err);
      }
    };

    this.ws.onclose = (event: CloseEvent) => {
      console.log("[WebSocketClient] Connection closed:", event.code, event.reason);
      this.ws = null;

      if (this.shouldReconnect) {
        this.scheduleReconnect();
      } else {
        this.setState("disconnected");
      }
    };

    this.ws.onerror = (event: Event) => {
      console.error("[WebSocketClient] Connection error:", event);
      // onclose will follow, which handles reconnect
    };
  }

  send(message: unknown): void {
    if (this.state !== "connected" || !this.ws) {
      console.warn("[WebSocketClient] Cannot send message, not connected. State:", this.state);
      return;
    }
    this.sendRaw(message);
  }

  private sendRaw(message: unknown): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      this.ws.send(JSON.stringify(message));
    } catch (err) {
      console.error("[WebSocketClient] Failed to send message:", err);
    }
  }

  onMessage(callback: MessageCallback): () => void {
    this.messageCallbacks.add(callback);
    return () => this.messageCallbacks.delete(callback);
  }

  onStateChange(callback: (state: ConnectionState) => void): () => void {
    this.stateCallbacks.add(callback);
    return () => this.stateCallbacks.delete(callback);
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this.connectMessage = null;
    this.cancelReconnect();
    this.cleanup();
    this.setState("disconnected");
  }

  setUrl(url: string): void {
    this.url = url;
  }

  private scheduleReconnect(): void {
    if (!this.shouldReconnect) return;

    this.setState("reconnecting");
    console.log(`[WebSocketClient] Reconnecting in ${this.reconnectDelay}ms...`);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.shouldReconnect) {
        this.doConnect();
      }
    }, this.reconnectDelay);

    // Exponential backoff
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
  }

  private cancelReconnect(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private cleanup(): void {
    if (this.ws) {
      // Remove listeners before closing to avoid triggering reconnect
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
      this.ws = null;
    }
  }
}
