---
name: agenda-semantic-analysis
description: Formalize agenda tracking from meeting transcripts and design explainable drift or completion logic. Use for algorithms, state models, schemas, prompts, or tests.
---

# Agenda semantic analysis

Represent the agenda as ordered items with stable IDs and explicit states (for example pending, active, covered, deferred). Represent transcript segments with stable IDs, timestamps, and partial/final status. Combine enough context to resolve references; coalesce partial updates instead of analyzing every token.

Establish a simple lexical or embedding baseline before adding an LLM classifier. Keep topical relevance, agenda-item coverage, and meeting drift as distinct judgments. A relevance score is an indicator, not proof of completion or off-topic behavior. Calibrate thresholds on labeled data. Aggregate evidence over time and use confirmation/hysteresis so one ASR error or false match cannot complete an item. Absence of mention is not evidence of completion.

Return a validated structured result that includes agenda item ID, state, evidence segment IDs, confidence, reason, and optional suggested hint. Reject unknown IDs and unsupported claims; let users dismiss hints. Explicitly handle uncertainty, deferred items, transcript corrections, and stale analysis.

Evaluate with session-level data splits, a baseline, and ablations. Report per-class precision/recall/F1, false-hint rate, missed transitions, latency percentiles, and confidence calibration; separately evaluate Ukrainian/English, code-switching, noise, and ASR errors. Do not present uncalibrated model scores as probabilities.

References: [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages) and [OpenAI Realtime transcription](https://developers.openai.com/api/docs/guides/realtime-transcription).
