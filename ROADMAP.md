# Roadmap

Nothing is released yet. aivoice started as the session half of jarvis-ai and continues here; jarvis-ai (the personal assistant)
lives in its own repository.

**Built**
- Ears and voice: Whisper, Kokoro, neural voice detection, echo cancellation, barge-in, waiting for the whole sentence.
- Claude Code sessions found without a plugin, replies read from transcripts, any terminal or app on macOS, tmux anywhere.
- Session commands by name: list, switch, status, read, ask (with approval), open a session (with approval).
- Loose wording through an optional local model (MLX, llama.cpp, Ollama, any OpenAI-compatible server), checked by plain code.
- Approval gate with an audit log. The model proposes; only you approve.
- Announcements when a background session finishes; start at login (`aivoice login on`).
- Any terminal tool through `aivoice run`, any output through `aivoice speak`.

**Next**
1. Read-back connectors: Codex CLI sessions, the Claude desktop app, Cursor, Gemini CLI, Copilot CLI.
2. A window: what was heard, open sessions and their state, pending approvals.
3. An announcement when a session is waiting for your permission.
4. Audio verified on Linux, Intel Macs and Windows (CI covers the portable logic only).
5. Auto-calibrated echo delay; prebuilt echo-canceller wheels; an installer.
