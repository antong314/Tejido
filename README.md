# Circle

AI-facilitated group deliberation prototype. See [PRD.md](PRD.md) for the full
product spec.

Six participants each have a 20–30 minute private conversation with a Telegram
bot about a shared question, decide per-point what may be shared with the
group, and reconvene in person to discuss a one-page synthesis the facilitator
generates from the transcripts.

## Architecture

Single Python process on the facilitator's laptop:

- **Bot** (`circle.bot`) — Telegram handlers for consent, conversation,
  permissions, and edge commands.
- **Synthesis script** (`circle.synthesis`) — separate CLI invoked during the
  break to produce a discussion synthesis (themes, divergences, outliers —
  what the group said).
- **Proposal script** (`circle.proposal`) — separate CLI that drafts concrete
  proposal language the group can react to and vote on (a draft + per-
  participant predicted vote signals + outstanding tensions). Run after
  synthesis when the group is ready to move from discussion to a decision.
- **Dashboard** (`circle.dashboard`) — separate CLI showing each participant's
  current phase and elapsed time. Shows zero conversation content.

Storage is one JSON file per participant under `data/<session_id>/`.

The only outbound API call is to **Anthropic**. Speech-to-text runs locally
via `pywhispercpp` (whisper.cpp) — no audio leaves the laptop.

## Prerequisites

- Python 3.11+
- `ffmpeg` on PATH — required to convert Telegram's `.ogg/Opus` voice notes
  to the 16 kHz mono WAV that whisper.cpp expects.
  - macOS: `brew install ffmpeg`
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - Windows: `choco install ffmpeg` or `scoop install ffmpeg`
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An Anthropic API key

## Setup

```bash
git clone <this repo>
cd Tejido

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and fill in ANTHROPIC_API_KEY and TELEGRAM_BOT_TOKEN

cp config/session_config.example.yaml config/session_config.yaml
# edit config/session_config.yaml — see field descriptions in the example
```

Real session configs are gitignored (`config/session_*.yaml` minus the
example) because they contain participant Telegram handles and
community-specific context. Keep them local.

The session config fields:

- `session_id` — short slug used in file names
- `question` — exact question the facilitator AI will explore with each
  participant. Multi-part numbered questions are supported and the synthesis
  / proposal output will organize by sub-question.
- `context` — optional background, only shown to participants if they ask
- `community_context` — optional, used by synthesis and proposal modes to
  ground the output in your community's specific context (shared values,
  prior decisions, named principles)
- `participants` — six `{handle, display_name}` entries; the handle is the
  Telegram `@username` (with or without the `@`)
- `whisper.model` — `tiny` / `base` / `small` / `medium` / `large-v3`. Default
  is `medium` (~1.5 GB, good Spanish + English on a modern laptop). The first
  run downloads the weights into `models/`.
- `facilitator_model` — Claude model for the per-participant conversation;
  default `claude-sonnet-4-5`.
- `synthesis_model` — Claude model for synthesis and proposal; recommended
  `claude-opus-4-7` (noticeably better than Sonnet on multi-part deliberation
  questions).

## Running a session

Open three terminals.

**Terminal 1 — bot:**

```bash
source .venv/bin/activate
PYTHONPATH=src python -m circle.bot --config config/session_config.yaml
```

The first launch downloads the whisper model (~1.5 GB for `medium`) into
`models/`. Subsequent launches are instant.

**Terminal 2 — dashboard:**

```bash
source .venv/bin/activate
PYTHONPATH=src python -m circle.dashboard --config config/session_config.yaml
```

Refreshes every two seconds and shows phase + duration per participant. No
conversation content is ever displayed.

**Terminal 3 — synthesis (only when ready):**

```bash
source .venv/bin/activate
PYTHONPATH=src python -m circle.synthesis --config config/session_config.yaml
```

Run during the break, after enough participants have reached `complete`.
Writes `syntheses/synthesis_YYYYMMDD.md`. Re-runs append a counter so you
never overwrite a previous synthesis (useful if a late finisher needs to be
included).

**Terminal 3 (or later) — proposal (optional):**

```bash
PYTHONPATH=src python -m circle.proposal --config config/session_config.yaml
```

Drafts concrete proposal language from the same transcripts, plus per-
participant predicted vote signals, outstanding tensions, and alternative
drafts. Use this when the group is ready to move from discussion to a
decision. Writes `proposals/proposal_YYYYMMDD.md`. Same anti-clobber
counter pattern as synthesis. Vote signals are LLM inferences, not actual
votes — treat the draft as a starting point to react to.

## Participant flow

| Phase | What happens |
|---|---|
| `not_started` | Pre-registered in YAML; they haven't sent `/start` yet. |
| `awaiting_consent` | Bot sent welcome + question; waiting for the "I'm ready" tap. |
| `in_conversation` | Facilitated AI conversation, text or voice. |
| `in_permissions` | 3–5 extracted points, each chosen "By name" / "Anonymous" / "Private". |
| `awaiting_addition` | "Anything to add?" yes/no. |
| `in_addition_permissions` | Granting permission for an addition. |
| `complete` | Done; transcript and permissions persisted. |

## Slash commands

- `/start` — begin (or, if already started, get a friendly nudge to keep going)
- `/help` — short pointer to the other commands
- `/done` — wrap up early; if it's been less than 5 minutes, the bot confirms
- `/permissions` — re-open the permissions walk-through (PRD §4.8)
- `/restart` — wipe state and start over (requires confirmation)

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Covers state-machine transitions and the synthesis filter — the two places
where a silent bug would corrupt the participant experience.

## Privacy

- Participant conversations are never visible to the facilitator during the
  session. The dashboard shows phase + duration only.
- Audio is transcribed locally via whisper.cpp and never leaves the laptop.
- Conversations and permissions are stored in plain JSON under `data/`.
- The only outbound API call is to Anthropic for the AI turns and the
  synthesis. The facilitator should communicate this clearly in the opening
  framing, per PRD §5.1.

## Out of scope

This is a prototype for a single 6-person session. PRD §6 lists the
deliberate non-goals: no accounts, no DB, no deployment, no WhatsApp, no
multi-session continuity, no scoring, no scaling beyond 6 participants.
