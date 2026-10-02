---
name: evaluation-experiments
description: Design reproducible accuracy, response-time, coordination, or usability evaluations for the meeting assistant. Use for datasets, labels, baselines, metrics, protocols, or result analysis.
---

# Evaluation experiments

Translate each thesis requirement into a hypothesis, controlled conditions, baseline, metric, and success criterion before examining test results. Define agenda scenarios and expected labels in advance (normal flow, topic drift/return, deferred or skipped items, interruptions, noise, and partial or erroneous transcripts). Document annotation rules and review a sample with a second annotator when feasible.

Evaluate ASR separately (WER with explicit normalization, plus critical-term errors), agenda judgments (per-class precision/recall/F1 and confusion matrix), hint quality (false-hint rate and missed opportunities), and full pipeline latency. Measure stage timings with a monotonic clock; report p50/p95, sample counts, timeouts, and dropped events. Do not call model-only latency end-to-end latency.

Compare a simple baseline and use ablations. Split train/calibration/test data by whole meeting session to prevent leakage. Record code, model, prompt, provider/region, configuration, date, environment, and dataset version. Report uncertainty and sample size; limit generalization when samples are small.

Obtain permission for real recordings, anonymize, restrict access, and set deletion periods. Prefer controlled or synthetic scenarios when suitable and state their limitations. Never invent measurements or claim improvement without the same evaluation set and a valid baseline.

Reference: [OpenAI Realtime transcription](https://developers.openai.com/api/docs/guides/realtime-transcription) and [Anthropic agent design](https://www.anthropic.com/engineering/building-effective-agents).
