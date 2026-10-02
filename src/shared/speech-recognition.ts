/**
 * Speech recognition service wrapping the Web Speech API.
 * Provides continuous speech recognition with automatic restart,
 * producing TranscriptSegment-compatible output.
 */

import type { TranscriptSegment } from "@/types/transcript";

// ---- Web Speech API TypeScript declarations ----
// These are not in standard TypeScript lib but are available in Chrome.

interface SpeechRecognitionResult {
  readonly length: number;
  readonly isFinal: boolean;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  readonly transcript: string;
  readonly confidence: number;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionEvent extends Event {
  readonly results: SpeechRecognitionResultList;
  readonly resultIndex: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string;
  readonly message: string;
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionInstance;
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

declare global {
  interface Window {
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
    SpeechRecognition?: SpeechRecognitionConstructor;
  }
}

// ---- Service ----

export type TranscriptCallback = (segment: TranscriptSegment) => void;

const DEFAULT_LANGUAGE = "uk-UA";
const DEFAULT_SPEAKER_ID = "local-user";
const RESTART_DELAY_MS = 300;
/** Errors that should not trigger an auto-restart */
const FATAL_ERRORS = new Set(["not-allowed", "service-not-allowed", "language-not-supported"]);

export class SpeechRecognitionService {
  private recognition: SpeechRecognitionInstance | null = null;
  private language: string;
  private meetingId = "";
  private isRunning = false;
  private shouldRestart = false;
  private segmentCounter = 0;
  private interimSegmentId: string | null = null;
  private callbacks: Set<TranscriptCallback> = new Set();
  private restartTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(language?: string) {
    this.language = language ?? DEFAULT_LANGUAGE;
  }

  /**
   * Check whether the Web Speech API is available in this browser.
   */
  isSupported(): boolean {
    return !!(window.webkitSpeechRecognition || window.SpeechRecognition);
  }

  /**
   * Set the meeting ID used in emitted TranscriptSegments.
   */
  setMeetingId(meetingId: string): void {
    this.meetingId = meetingId;
  }

  /**
   * Set the recognition language (e.g. "uk-UA", "en-US").
   */
  setLanguage(language: string): void {
    this.language = language;
    // If currently running, restart with the new language
    if (this.isRunning) {
      this.stopInternal();
      this.startInternal();
    }
  }

  /**
   * Register a callback for transcript segments.
   * Returns an unsubscribe function.
   */
  onTranscript(callback: TranscriptCallback): () => void {
    this.callbacks.add(callback);
    return () => this.callbacks.delete(callback);
  }

  /**
   * Start continuous speech recognition.
   */
  start(): void {
    if (this.isRunning) return;

    if (!this.isSupported()) {
      console.error("[SpeechRecognition] Web Speech API is not supported in this browser");
      return;
    }

    this.shouldRestart = true;
    this.isRunning = true;
    this.startInternal();
  }

  /**
   * Stop speech recognition.
   */
  stop(): void {
    this.shouldRestart = false;
    this.isRunning = false;
    this.cancelRestart();
    this.stopInternal();
  }

  private startInternal(): void {
    const SpeechRecognitionCtor = window.webkitSpeechRecognition || window.SpeechRecognition;
    if (!SpeechRecognitionCtor) return;

    this.recognition = new SpeechRecognitionCtor();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = this.language;
    this.recognition.maxAlternatives = 1;

    this.recognition.onresult = (event: SpeechRecognitionEvent) => {
      this.handleResult(event);
    };

    this.recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      console.warn("[SpeechRecognition] Error:", event.error, event.message);

      if (FATAL_ERRORS.has(event.error)) {
        console.error("[SpeechRecognition] Fatal error, stopping:", event.error);
        this.shouldRestart = false;
        this.isRunning = false;
      }
      // For non-fatal errors (e.g. "no-speech", "network", "aborted"),
      // the onend handler will trigger a restart if shouldRestart is true.
    };

    this.recognition.onend = () => {
      if (this.shouldRestart && this.isRunning) {
        // Auto-restart after a short delay (SpeechRecognition stops after silence)
        this.restartTimer = setTimeout(() => {
          this.restartTimer = null;
          if (this.shouldRestart && this.isRunning) {
            console.log("[SpeechRecognition] Auto-restarting...");
            this.startInternal();
          }
        }, RESTART_DELAY_MS);
      }
    };

    this.recognition.onstart = () => {
      console.log("[SpeechRecognition] Started, language:", this.language);
    };

    try {
      this.recognition.start();
    } catch (err) {
      console.error("[SpeechRecognition] Failed to start:", err);
      // Schedule a restart
      if (this.shouldRestart) {
        this.restartTimer = setTimeout(() => {
          this.restartTimer = null;
          if (this.shouldRestart && this.isRunning) {
            this.startInternal();
          }
        }, RESTART_DELAY_MS);
      }
    }
  }

  private stopInternal(): void {
    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch {
        // ignore — may already be stopped
      }
      this.recognition.onresult = null;
      this.recognition.onerror = null;
      this.recognition.onend = null;
      this.recognition.onstart = null;
      this.recognition = null;
    }
  }

  private cancelRestart(): void {
    if (this.restartTimer !== null) {
      clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }
  }

  private handleResult(event: SpeechRecognitionEvent): void {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      const alternative = result[0];

      if (!alternative || !alternative.transcript.trim()) continue;

      const isFinal = result.isFinal;

      let segmentId: string;
      if (isFinal) {
        // Use the interim ID if we have one, otherwise generate a new one
        segmentId = this.interimSegmentId ?? this.generateSegmentId();
        this.interimSegmentId = null;
      } else {
        // For interim results, reuse or create an ID for this ongoing utterance
        if (!this.interimSegmentId) {
          this.interimSegmentId = this.generateSegmentId();
        }
        segmentId = this.interimSegmentId;
      }

      const segment: TranscriptSegment = {
        id: segmentId,
        meetingId: this.meetingId,
        speakerId: DEFAULT_SPEAKER_ID,
        text: alternative.transcript.trim(),
        timestamp: Date.now(),
        isFinal,
        confidence: isFinal ? alternative.confidence : undefined,
        version: isFinal ? 1 : 0,
      };

      this.emitSegment(segment);

      // If this was a final result, reset the interim tracking
      // so the next interim result gets a new ID
      if (isFinal) {
        this.interimSegmentId = null;
      }
    }
  }

  private generateSegmentId(): string {
    this.segmentCounter++;
    // Use crypto.randomUUID if available, otherwise fall back to counter-based ID
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    return `seg-${Date.now()}-${this.segmentCounter}`;
  }

  private emitSegment(segment: TranscriptSegment): void {
    for (const cb of this.callbacks) {
      try {
        cb(segment);
      } catch (err) {
        console.error("[SpeechRecognition] Callback error:", err);
      }
    }
  }
}
