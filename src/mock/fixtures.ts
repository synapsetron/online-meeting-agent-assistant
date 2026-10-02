import type { AgendaItem } from "@/types/agenda";
import { AgendaItemStatus } from "@/types/agenda";
import type { Speaker, TranscriptSegment } from "@/types/transcript";
import type { Hint } from "@/types/hint";
import { HintType } from "@/types/hint";

export const MEETING_ID = "meeting-001";

export const SPEAKERS: Speaker[] = [
  { id: "speaker-01", name: "Olena K.", color: "#3B82F6" },
  { id: "speaker-02", name: "Dmytro S.", color: "#10B981" },
  { id: "speaker-03", name: "Prof. Ivanov", color: "#F59E0B" },
];

export const AGENDA_ITEMS: AgendaItem[] = [
  {
    id: "agenda-001",
    title: "Project overview",
    description: "Brief introduction and goals of the meeting assistant",
    status: AgendaItemStatus.Pending,
    estimatedMinutes: 5,
    elapsedSeconds: 0,
    evidence: [],
    order: 1,
  },
  {
    id: "agenda-002",
    title: "Architecture review",
    description: "Discuss the system architecture and component interactions",
    status: AgendaItemStatus.Pending,
    estimatedMinutes: 10,
    elapsedSeconds: 0,
    evidence: [],
    order: 2,
  },
  {
    id: "agenda-003",
    title: "ASR integration",
    description: "Speech recognition provider comparison and selection",
    status: AgendaItemStatus.Pending,
    estimatedMinutes: 8,
    elapsedSeconds: 0,
    evidence: [],
    order: 3,
  },
  {
    id: "agenda-004",
    title: "Evaluation protocol",
    description: "Define metrics, datasets, and success criteria",
    status: AgendaItemStatus.Pending,
    estimatedMinutes: 10,
    elapsedSeconds: 0,
    evidence: [],
    order: 4,
  },
  {
    id: "agenda-005",
    title: "Timeline & milestones",
    description: "Review deadlines and deliverables",
    status: AgendaItemStatus.Pending,
    estimatedMinutes: 5,
    elapsedSeconds: 0,
    evidence: [],
    order: 5,
  },
  {
    id: "agenda-006",
    title: "Open questions",
    description: "Discussion of unresolved issues and next steps",
    status: AgendaItemStatus.Pending,
    estimatedMinutes: 7,
    elapsedSeconds: 0,
    evidence: [],
    order: 6,
  },
];

export const TRANSCRIPT_SEGMENTS: TranscriptSegment[] = [
  { id: "seg-001", meetingId: MEETING_ID, speakerId: "speaker-01", text: "Good morning everyone. Let's get started with today's meeting.", timestamp: 0, isFinal: true, confidence: 0.95, version: 1 },
  { id: "seg-002", meetingId: MEETING_ID, speakerId: "speaker-01", text: "The main goal of our project is to build an intelligent assistant for online meetings.", timestamp: 5000, isFinal: true, confidence: 0.92, version: 1 },
  { id: "seg-003", meetingId: MEETING_ID, speakerId: "speaker-03", text: "Can you briefly summarize the key features you're planning?", timestamp: 12000, isFinal: true, confidence: 0.94, version: 1 },
  { id: "seg-004", meetingId: MEETING_ID, speakerId: "speaker-01", text: "Of course. We have agenda tracking, real-time transcription, and AI-powered hints.", timestamp: 16000, isFinal: true, confidence: 0.91, version: 1 },
  { id: "seg-005", meetingId: MEETING_ID, speakerId: "speaker-02", text: "I'd like to add that we also plan to evaluate the system against measurable metrics.", timestamp: 22000, isFinal: true, confidence: 0.93, version: 1 },

  { id: "seg-006", meetingId: MEETING_ID, speakerId: "speaker-01", text: "Let's move on to the architecture review. Here is the high-level component diagram.", timestamp: 30000, isFinal: true, confidence: 0.96, version: 1 },
  { id: "seg-007", meetingId: MEETING_ID, speakerId: "speaker-01", text: "The system has six main layers: audio capture, ASR, transcript management, agenda analysis, hint validation, and UI.", timestamp: 35000, isFinal: true, confidence: 0.90, version: 1 },
  { id: "seg-008", meetingId: MEETING_ID, speakerId: "speaker-02", text: "For the browser extension, we're using Chrome Manifest V3 with a content script overlay.", timestamp: 42000, isFinal: true, confidence: 0.94, version: 1 },
  { id: "seg-009", meetingId: MEETING_ID, speakerId: "speaker-03", text: "How are you handling the isolation between the extension UI and Google Meet's page?", timestamp: 48000, isFinal: true, confidence: 0.92, version: 1 },
  { id: "seg-010", meetingId: MEETING_ID, speakerId: "speaker-02", text: "We use Shadow DOM to encapsulate all our styles and elements. This prevents any CSS conflicts.", timestamp: 53000, isFinal: true, confidence: 0.91, version: 1 },
  { id: "seg-011", meetingId: MEETING_ID, speakerId: "speaker-03", text: "Good approach. What about the communication between the content script and the background worker?", timestamp: 60000, isFinal: true, confidence: 0.95, version: 1 },
  { id: "seg-012", meetingId: MEETING_ID, speakerId: "speaker-01", text: "We use Chrome runtime messaging with typed message contracts for all communication.", timestamp: 65000, isFinal: true, confidence: 0.93, version: 1 },

  { id: "seg-013", meetingId: MEETING_ID, speakerId: "speaker-01", text: "Now, regarding the speech recognition integration...", timestamp: 75000, isFinal: true, confidence: 0.92, version: 1 },
  { id: "seg-014", meetingId: MEETING_ID, speakerId: "speaker-02", text: "We evaluated three providers: OpenAI Whisper, Google Cloud Speech, and a local Vosk model.", timestamp: 80000, isFinal: true, confidence: 0.91, version: 1 },
  { id: "seg-015", meetingId: MEETING_ID, speakerId: "speaker-02", text: "OpenAI's realtime API offers the best accuracy for our target languages: Ukrainian and English.", timestamp: 87000, isFinal: true, confidence: 0.94, version: 1 },
  { id: "seg-016", meetingId: MEETING_ID, speakerId: "speaker-03", text: "What about latency? Real-time meetings require sub-second transcription.", timestamp: 93000, isFinal: true, confidence: 0.93, version: 1 },
  { id: "seg-017", meetingId: MEETING_ID, speakerId: "speaker-02", text: "Our benchmarks show p50 at 340ms and p95 at 620ms for the streaming mode.", timestamp: 98000, isFinal: true, confidence: 0.90, version: 1 },

  { id: "seg-018", meetingId: MEETING_ID, speakerId: "speaker-03", text: "By the way, have we considered the budget implications of the cloud APIs?", timestamp: 106000, isFinal: true, confidence: 0.92, version: 1 },
  { id: "seg-019", meetingId: MEETING_ID, speakerId: "speaker-01", text: "That's a good point, but let's discuss that when we get to timeline and milestones.", timestamp: 110000, isFinal: true, confidence: 0.91, version: 1 },

  { id: "seg-020", meetingId: MEETING_ID, speakerId: "speaker-01", text: "Let's discuss our evaluation protocol now. What metrics should we prioritize?", timestamp: 120000, isFinal: true, confidence: 0.95, version: 1 },
  { id: "seg-021", meetingId: MEETING_ID, speakerId: "speaker-02", text: "For ASR we should measure WER with fixed normalization on our test set.", timestamp: 126000, isFinal: true, confidence: 0.93, version: 1 },
  { id: "seg-022", meetingId: MEETING_ID, speakerId: "speaker-02", text: "For agenda tracking, I propose per-class precision, recall, and F1 score.", timestamp: 132000, isFinal: true, confidence: 0.94, version: 1 },
  { id: "seg-023", meetingId: MEETING_ID, speakerId: "speaker-03", text: "Don't forget latency. We need end-to-end audio-to-visible-hint measurements.", timestamp: 138000, isFinal: true, confidence: 0.92, version: 1 },
  { id: "seg-024", meetingId: MEETING_ID, speakerId: "speaker-01", text: "Agreed. We'll report p50 and p95 for each pipeline stage separately.", timestamp: 143000, isFinal: true, confidence: 0.91, version: 1 },

  { id: "seg-025", meetingId: MEETING_ID, speakerId: "speaker-01", text: "Moving on to timeline. Our thesis defense is scheduled for January.", timestamp: 155000, isFinal: true, confidence: 0.96, version: 1 },
  { id: "seg-026", meetingId: MEETING_ID, speakerId: "speaker-02", text: "The first milestone is the fixture-based vertical slice, which should be ready by mid-November.", timestamp: 160000, isFinal: true, confidence: 0.93, version: 1 },
  { id: "seg-027", meetingId: MEETING_ID, speakerId: "speaker-03", text: "That sounds tight. Make sure to allocate extra time for the evaluation chapter.", timestamp: 166000, isFinal: true, confidence: 0.91, version: 1 },

  { id: "seg-028", meetingId: MEETING_ID, speakerId: "speaker-01", text: "Finally, any open questions before we wrap up?", timestamp: 178000, isFinal: true, confidence: 0.94, version: 1 },
  { id: "seg-029", meetingId: MEETING_ID, speakerId: "speaker-03", text: "I'd like to see a demo of the overlay at our next meeting.", timestamp: 183000, isFinal: true, confidence: 0.93, version: 1 },
  { id: "seg-030", meetingId: MEETING_ID, speakerId: "speaker-01", text: "Absolutely. We'll have the preview page ready. Thank you everyone!", timestamp: 188000, isFinal: true, confidence: 0.95, version: 1 },
];

export const HINTS: Hint[] = [
  {
    id: "hint-001",
    type: HintType.AgendaSuggestion,
    agendaItemId: "agenda-002",
    message: "The speaker is introducing system components. Consider transitioning to the architecture review item.",
    evidenceSegmentIds: ["seg-004"],
    confidence: 0.85,
    timestamp: 20000,
    dismissed: false,
  },
  {
    id: "hint-002",
    type: HintType.AgendaSuggestion,
    agendaItemId: "agenda-003",
    message: "Discussion has shifted to speech recognition. The ASR integration item may be starting.",
    evidenceSegmentIds: ["seg-013"],
    confidence: 0.90,
    timestamp: 76000,
    dismissed: false,
  },
  {
    id: "hint-003",
    type: HintType.TopicDrift,
    agendaItemId: "agenda-003",
    message: "Budget discussion detected, but this is not part of the current agenda item. The speaker may be drifting from ASR integration.",
    evidenceSegmentIds: ["seg-018"],
    confidence: 0.78,
    uncertainty: "Budget could be relevant to provider selection.",
    timestamp: 107000,
    dismissed: false,
  },
  {
    id: "hint-004",
    type: HintType.TimeWarning,
    agendaItemId: "agenda-002",
    message: "Architecture review has exceeded its estimated 10-minute duration by 3 minutes.",
    evidenceSegmentIds: ["seg-012"],
    confidence: 0.95,
    timestamp: 70000,
    dismissed: false,
  },
  {
    id: "hint-005",
    type: HintType.AgendaSuggestion,
    agendaItemId: "agenda-004",
    message: "Evaluation metrics are being discussed. The evaluation protocol item appears to be active.",
    evidenceSegmentIds: ["seg-020", "seg-021"],
    confidence: 0.92,
    timestamp: 122000,
    dismissed: false,
  },
  {
    id: "hint-006",
    type: HintType.MissedItem,
    agendaItemId: "agenda-005",
    message: "Timeline & milestones was briefly touched but has not been formally covered. Consider revisiting.",
    evidenceSegmentIds: ["seg-025", "seg-026"],
    confidence: 0.72,
    uncertainty: "Some timeline information was shared, but the item may not be fully covered.",
    timestamp: 170000,
    dismissed: false,
  },
  {
    id: "hint-007",
    type: HintType.Summary,
    agendaItemId: "agenda-006",
    message: "Meeting appears to be wrapping up. 4 of 6 agenda items were covered, 1 deferred, 1 partially discussed.",
    evidenceSegmentIds: ["seg-028"],
    confidence: 0.88,
    timestamp: 180000,
    dismissed: false,
  },
];
