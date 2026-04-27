# Tejido

AI-facilitated group deliberation prototype. See [PRD.md](PRD.md) for the full
product spec.

## Why Tejido

**The name.** *Tejido* is Spanish for "weave" or "fabric" — the cloth you get
when many separate threads come together with care, each one still visible in
the whole. That's the metaphor. Every participant in a group has something to
say; a good deliberation doesn't average their voices into mush, it weaves
them together so the group sees the whole fabric without losing any one
thread. (This repo holds *Circle*, the first concrete implementation: a small
Telegram bot for one 6-person session at a time. Tejido is the broader
project — the same weaving principle applied at different scales and through
different channels.)

**The problem.** Groups facing real decisions usually fall into one of two
failure modes:

1. **Long group discussion threads** (WhatsApp, Telegram, group email).
   Organic, easy to start, low effort. But the loudest voices dominate, the
   earliest commenters anchor the framing, the quiet ones stay silent, nuance
   is lost in length, and after a hundred messages nobody holds the whole
   picture in their head. The thread becomes about who's persuasive, not
   about what's true or what matters most.

2. **Voting and surveys.** Clean and decisive, but they flatten nuance.
   "Support" / "oppose" doesn't capture "I support this for reason X but
   would prefer Y" or "I oppose because of one specific caveat." A tally
   shows the headline but hides the texture — you don't know *why* people
   voted as they did, what they cared about, or what would change their
   mind. And surveys can only measure positions; they can't help anyone
   develop one.

Both approaches treat the group as either too connected (everyone shouting
in one thread) or too disconnected (numbers in a tally with no story). The
slow, careful middle is missing: each person gets the time and attention to
articulate what they actually think, and the group then sees those threads
woven together without losing the people behind them.

**What Tejido does.** Each participant has a private 20–30 minute
conversation with a thoughtful AI facilitator about the same question. They
think out loud — including the parts they haven't worked out — without
performing for the group. They choose, point by point, what gets shared
(by name, anonymously, or kept private). The system then weaves the
conversations into a one-page synthesis (or a concrete draft proposal) the
facilitator reads aloud when the group reconvenes in person.

|                                       | Long discussion thread | Vote / survey   | Tejido               |
| ------------------------------------- | ---------------------- | --------------- | -------------------- |
| Every voice gets real room            | No                     | Briefly         | Yes — deeply         |
| Captures nuance                       | In theory              | No              | Yes                  |
| Group can actually read it            | After 50 msgs, no      | Yes             | Yes (one page)       |
| Surfaces the *why*, not just position | Sometimes              | No              | Yes                  |
| Surfaces real disagreement            | Buried in scroll       | Just the tally  | Explicitly named     |
| Loudest voices dominate               | Yes                    | No              | No                   |
| Time cost                             | Asynchronous, ongoing  | Minutes         | One sitting          |
| Replaces the in-person meeting        | Often does, badly      | Sometimes       | No — sets it up      |

Tejido is not a replacement for the group meeting. It's an instrument the
facilitator uses to bring better material *into* the meeting — so when the
group sits down together, every voice is already in the room and the
facilitator can spend the time on real disagreement instead of on getting
people to speak up.

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
