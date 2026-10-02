import type { Scenario, ScenarioEvent } from "./meeting-simulator";
import {
  SPEAKERS,
  AGENDA_ITEMS,
  TRANSCRIPT_SEGMENTS,
  HINTS,
} from "./fixtures";
import { AgendaItemStatus } from "@/types/agenda";
import { HintType } from "@/types/hint";

function buildNormalFlow(): Scenario {
  const events: ScenarioEvent[] = [];

  events.push({
    timeMs: 500,
    action: { type: "agenda_transition", itemId: "agenda-001", status: AgendaItemStatus.Active },
  });

  for (const seg of TRANSCRIPT_SEGMENTS) {
    if (seg.timestamp < 5000) {
      events.push({
        timeMs: seg.timestamp + 500,
        action: {
          type: "transcript_partial",
          segment: { ...seg, text: seg.text.slice(0, Math.floor(seg.text.length * 0.6)), isFinal: false, version: 0 },
        },
      });
    }

    events.push({
      timeMs: seg.timestamp + 1500,
      action: { type: "transcript", segment: seg },
    });
  }

  events.push({
    timeMs: 28000,
    action: { type: "agenda_transition", itemId: "agenda-002", status: AgendaItemStatus.Active },
  });

  events.push({
    timeMs: 20000,
    action: { type: "hint", hint: HINTS[0] },
  });

  events.push({
    timeMs: 70000,
    action: { type: "hint", hint: HINTS[3] },
  });

  events.push({
    timeMs: 73000,
    action: { type: "agenda_transition", itemId: "agenda-003", status: AgendaItemStatus.Active },
  });

  events.push({
    timeMs: 76000,
    action: { type: "hint", hint: HINTS[1] },
  });

  events.push({
    timeMs: 107000,
    action: { type: "hint", hint: HINTS[2] },
  });

  events.push({
    timeMs: 118000,
    action: { type: "agenda_transition", itemId: "agenda-004", status: AgendaItemStatus.Active },
  });

  events.push({
    timeMs: 122000,
    action: { type: "hint", hint: HINTS[4] },
  });

  events.push({
    timeMs: 153000,
    action: { type: "agenda_transition", itemId: "agenda-005", status: AgendaItemStatus.Active },
  });

  events.push({
    timeMs: 170000,
    action: { type: "hint", hint: HINTS[5] },
  });

  events.push({
    timeMs: 175000,
    action: { type: "agenda_transition", itemId: "agenda-006", status: AgendaItemStatus.Active },
  });

  events.push({
    timeMs: 180000,
    action: { type: "hint", hint: HINTS[6] },
  });

  events.sort((a, b) => a.timeMs - b.timeMs);

  return { speakers: SPEAKERS, agendaItems: AGENDA_ITEMS, events };
}

function buildTopicDrift(): Scenario {
  const base = buildNormalFlow();
  const items = structuredClone(base.agendaItems);
  const events = base.events.slice(0, 18);

  events.push({
    timeMs: 40000,
    action: {
      type: "hint",
      hint: {
        id: "hint-drift-01",
        type: HintType.TopicDrift,
        agendaItemId: "agenda-002",
        message: "Discussion appears to have drifted to implementation details. The current item is architecture review.",
        evidenceSegmentIds: ["seg-008"],
        confidence: 0.82,
        timestamp: 40000,
        dismissed: false,
      },
    },
  });

  events.sort((a, b) => a.timeMs - b.timeMs);
  return { speakers: SPEAKERS, agendaItems: items, events };
}

function buildDeferredItems(): Scenario {
  const base = buildNormalFlow();
  const items = structuredClone(base.agendaItems);
  const events = base.events.slice();

  events.push({
    timeMs: 115000,
    action: { type: "agenda_transition", itemId: "agenda-003", status: AgendaItemStatus.Deferred },
  });

  events.push({
    timeMs: 170000,
    action: { type: "agenda_transition", itemId: "agenda-005", status: AgendaItemStatus.Skipped },
  });

  events.sort((a, b) => a.timeMs - b.timeMs);
  return { speakers: SPEAKERS, agendaItems: items, events };
}

function buildQuickMeeting(): Scenario {
  const speakers = SPEAKERS.slice(0, 2);
  const items = AGENDA_ITEMS.slice(0, 3).map((item) => ({
    ...structuredClone(item),
    estimatedMinutes: 2,
  }));

  const events: ScenarioEvent[] = [
    { timeMs: 300, action: { type: "agenda_transition", itemId: "agenda-001", status: AgendaItemStatus.Active } },
    { timeMs: 1000, action: { type: "transcript", segment: { ...TRANSCRIPT_SEGMENTS[0], timestamp: Date.now() } } },
    { timeMs: 3000, action: { type: "transcript", segment: { ...TRANSCRIPT_SEGMENTS[1], timestamp: Date.now() + 2000 } } },
    { timeMs: 6000, action: { type: "agenda_transition", itemId: "agenda-002", status: AgendaItemStatus.Active } },
    { timeMs: 7000, action: { type: "transcript", segment: { ...TRANSCRIPT_SEGMENTS[6], timestamp: Date.now() + 6000 } } },
    { timeMs: 10000, action: { type: "transcript", segment: { ...TRANSCRIPT_SEGMENTS[7], timestamp: Date.now() + 9000 } } },
    { timeMs: 13000, action: { type: "agenda_transition", itemId: "agenda-003", status: AgendaItemStatus.Active } },
    { timeMs: 14000, action: { type: "transcript", segment: { ...TRANSCRIPT_SEGMENTS[13], timestamp: Date.now() + 13000 } } },
    { timeMs: 17000, action: { type: "transcript", segment: { ...TRANSCRIPT_SEGMENTS[14], timestamp: Date.now() + 16000 } } },
    { timeMs: 20000, action: { type: "hint", hint: { ...HINTS[6], id: "hint-quick-01", timestamp: Date.now() + 19000 } } },
  ];

  return { speakers, agendaItems: items, events };
}

export const SCENARIOS = {
  normalFlow: buildNormalFlow(),
  topicDrift: buildTopicDrift(),
  deferredItems: buildDeferredItems(),
  quickMeeting: buildQuickMeeting(),
} as const;

export type ScenarioName = keyof typeof SCENARIOS;
