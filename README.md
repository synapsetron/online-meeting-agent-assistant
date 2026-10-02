# Online meeting agent assistant

This repository is the starting point for a master's thesis project: an intelligent assistant for online meetings, with agenda-aware context monitoring, a browser-extension integration for Google Meet, streaming speech-to-text, LLM-based analysis, and evaluation of accuracy and response time.

The application is not implemented yet. Treat these as project goals, not as existing features, test results, or validated design decisions. Confirm requirements against the approved thesis assignment when it is available.

## Getting started

There is no application setup or run command yet. Start by reviewing the repository and thesis requirements, then propose a small, testable baseline before choosing frameworks, providers, or adding dependencies. Keep implementation decisions and measurable results traceable to evidence.

Use [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) from the repository root. It reads [`CLAUDE.md`](CLAUDE.md) for project-wide guidance. The focused skills in [`.claude/skills/`](.claude/skills/) are available as `/thesis-research`, `/multi-agent-design`, `/agenda-semantic-analysis`, `/meet-extension-integration`, `/llm-realtime-integration`, `/evaluation-experiments`, `/thesis-compliance`, and `/thesis-defense`; Claude may also load a relevant skill automatically. Ask for one focused task at a time, such as reviewing API feasibility, specifying an agenda-state baseline, or designing an evaluation protocol.

## Reference documentation

- [Anthropic Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Chrome `tabCapture` API](https://developer.chrome.com/docs/extensions/reference/api/tabCapture) and [extension permissions](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions)
- [Google Meet API overview](https://developers.google.com/workspace/meet/api/guides/overview)
- [OpenAI Realtime transcription](https://developers.openai.com/api/docs/guides/realtime-transcription)
- [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages) and [tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
