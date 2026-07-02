# Claude Local Phone Control

This project is controlled from the Mac and, when mobile mode is on, from the user's iPhone through iMessage.

## Phone Mode

Phone mode is active when this file exists:

```bash
~/.claude/imessage-agent-on
```

Incoming iMessages are pasted into this Claude Code session by:

```bash
~/.claude/imessage-listener.sh
```

When phone mode is active:

- Treat each incoming pasted message as a command from the user.
- Do the requested task on the Mac whenever it is safe and clear.
- Send a short result back to the phone with:

```bash
bash ~/.claude/imessage-send.sh "Done — <short result>. Need anything else?"
```

- Keep phone replies to 1-3 short sentences.
- Do not send long logs, code blocks, or multi-paragraph explanations to the phone.
- Keep detailed work in the Terminal transcript.
- If a command is unclear, ask one short question by iMessage.
- If the user texts `stop`, mobile mode is handled by the listener and should turn off.

## Useful Phone Commands

Examples of commands that should work from the phone:

- `say hello`
- `what is the local model status?`
- `run git status`
- `start the local model`
- `open the dashboard`
- `send me a screenshot`

## Local Stack

The local model server runs on:

```text
http://localhost:4000
```

The dashboard runs on:

```text
http://127.0.0.1:4899
```

The phone iMessage route is configured at:

```bash
~/.claude/screen-to-phone-config.sh
```
