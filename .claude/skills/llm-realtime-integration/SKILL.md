---
name: llm-realtime-integration
description: Integrate streaming speech recognition and LLM analysis in a low-latency meeting assistant. Use for ASR/provider adapters, streaming events, deadlines, API boundaries, or fallbacks.
---

# Realtime ASR and LLM integration

Separate audio acquisition, speech-to-text, transcript/context management, semantic analysis, validation, and UI delivery behind testable interfaces. ASR transcribes speech; Anthropic Messages handles language-model input and tool use, not speech recognition. Compare ASR providers using representative target-language audio rather than assuming quality.

Define typed events with stable segment/item IDs, versions, timestamps, and partial/final status. Coalesce partials; analyze finalized segments or meaningful changes. Bound context and call frequency, and discard stale outputs. Set per-stage and end-to-end deadlines; handle timeout, cancellation, rate limiting, provider errors, disconnects, malformed output, and backpressure explicitly. Retry only safe operations with bounded backoff.

Validate structured model output, IDs, evidence, and freshness before display. Never present unverified partial output as a final hint. Measure capture-to-transcript, analysis, validation/render, and end-to-end capture-to-hint latency separately; report quantiles as well as failure/drop counts.

Keep credentials server-side, use least privilege, redact logs, secure consent, and minimize retention. Test language variation, noise, accents, code-switching, short utterances, and transcription corrections. Confirm current API event fields, model behavior, limits, and versioning in official docs during implementation.

References: [OpenAI Realtime transcription](https://developers.openai.com/api/docs/guides/realtime-transcription), [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages), [Anthropic streaming](https://platform.claude.com/docs/en/build-with-claude/streaming), and [tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview).
