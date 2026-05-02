# Tejido

AI-facilitated group deliberation. See [PRD.md](PRD.md) for the full
product spec.

## Why Tejido

**The name.** *Tejido* is Spanish for "weave" or "fabric" — the cloth you get
when many separate threads come together with care, each one still visible in
the whole. That's the metaphor. Every participant in a group has something to
say; a good deliberation doesn't average their voices into mush, it weaves
them together so the group sees the whole fabric without losing any one
thread.

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

**What Tejido does.** Each participant has a private 5–20 minute
conversation with a thoughtful AI facilitator about the same question. They
think out loud — including the parts they haven't worked out — without
performing for the group. They choose, point by point, what gets shared
(by name, anonymously, or kept private). The system then weaves the
conversations into a one-page synthesis (or a concrete draft proposal, or
a revised version of the document) the facilitator reads aloud when the
group reconvenes in person.

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

## Admin Guide

You'll spend most of your time in the admin UI at `/admin`. Here's the
mental model and the workflow.

### The four concepts

**Workflow types** are the three kinds of conversation Tejido supports.
You don't create them — they're built in — but you can edit how each
one talks (more on that under "Tuning the AI" below):

- **Open discussion.** A free-form facilitated conversation around a
  question. Output is a *synthesis*: themes the group converged on, where
  they split, individual outliers worth hearing. Use this when the group
  is exploring something for the first time and you want to understand
  the texture of how everyone thinks about it.
- **Decision drafting.** Pulls each participant toward concrete positions
  they could vote on. Output is a *draft proposal* — actual language the
  group could adopt — plus a per-participant predicted vote signal and
  a list of unresolved tensions. Use this when the group is past the
  "what do we think" phase and ready to move toward an actual decision.
- **Document revision.** Each participant reacts to a specific document
  (a charter, bylaw, mission statement, etc.). Output is a *revised
  document* — version 2 — with notes on what changed, what was kept
  despite pushback, and what was left for the group to resolve. Use
  this when you have something written that needs to evolve.

**Sessions** are the actual instances. One session per real-world
conversation. You pick a workflow type, fill in the question / document /
sub-questions, get back a participant URL, share it. Each session has its
own data and its own output files. You can have many sessions running at
once — each participant only ever sees the URL they were given.

**Contexts** (the **Context Library** in the top nav) are reusable
community-grounding blobs — shared values, prior decisions, named
principles, anything the synthesis output should anchor itself in. One
context per community is typical; the same context attaches to every
session you run for that community via the dropdown on the session form.
Optional — sessions without a context still work, the synthesis just
loses that grounding. Context is purely about WHO the community is, so
it's reusable across all three workflow types.

**Participants** join a session by visiting its URL and entering a
display name. There's no signup, no password, no account. Their
conversation is private — you (the admin) cannot see it while it's
happening. Each participant stays anonymous to other participants.

### What you actually do, in order

**Before the meeting (a day or a week before).**

1. **First time for this community?** Open **Contexts** in the top nav,
   create a context for them — a paragraph or two about their shared
   values, prior decisions, named principles. You'll reuse this for
   every session you run for that community. Skip this if you don't
   have anything community-specific to ground the synthesis in.
2. Open `/admin`, click **+ New workflow**, pick a workflow type.
3. Fill in the form: a short id (used in URLs), a title (for your own
   reference), and the workflow-specific data (the question, or the
   document you want revised).
4. Pick the **community context** from the dropdown (or leave as "None").
5. Set the conversation depth — minimal (2–3 min), medium (5–10 min),
   or deep (10–20 min). This drives how patiently the AI probes.
6. Save. You'll land on the session edit page.
7. Copy the **Participant URL** (the box at the top) and share it with
   the group however you usually communicate — email, Signal, whatever.
   They click the link, enter their name, and they're in.

**Optionally — Telegram instead of (or alongside) the web.** If you
want participants to use Telegram instead of the web link, scroll to
the **Telegram bot** card on the Sessions list page, pick this session
in the dropdown, click **Bind**. Telegram will route incoming messages
to that session until you change it. (Only one session at a time on
Telegram — it's a single-bot-token limitation. Web supports unlimited
parallel sessions.)

**While participants are in conversation.**

You don't have to do anything. The participants table on the session
edit page updates as people join, get partway through, and finish. It
shows phase, total time, turn count, and word count per participant.
Click any row to see that participant's full transcript and which
points they marked by-name / anonymous / private. Read these *after*
the session if you want — there's no obligation.

**After enough participants have finished.**

Once you have at least two or three completed conversations, click the
**Run [synthesis|proposal|revise]** button on the session page. (The
button is named after whichever output the workflow produces.) The
output appears in the "Past outputs" list within 30–90 seconds. Click
the filename to view the rendered markdown. You can re-run later if
late finishers come in — each run is timestamped, nothing is
overwritten.

**At the in-person meeting.**

Open the latest output, read the headline section aloud as your opening,
then walk the group through the rest. The output respects every
participant's permission choice — anonymous content stays anonymous,
private content is excluded entirely. The point is to bring everyone
into the room before the conversation even starts, so the group spends
its time on real disagreement instead of on getting people to speak up.

### Tuning the AI (advanced — usually skip)

The **Workflows** page (in the top nav) lets you edit the three big
prompt fragments that drive each workflow type:

- **Task framing** — the "what kind of conversation are we having"
  wrapper around every facilitator turn.
- **Output template** — the system prompt for the post-conversation
  processor (synthesis / proposal / revise).
- **Conversation mechanics** — how the AI probes, paces, and decides
  when to wrap up.

You usually leave these alone — the defaults are the result of careful
tuning. Edit them if you want to specialize a workflow for your
community's voice (e.g. tighter probing, a more clinical tone, output
formatted differently). Empty fields fall back to the default.

Editing applies to **every** session of that workflow type — so think
of these as your community's preferences, not per-session knobs.

### Common operational gotchas

- **Hard-refresh the participant page** after you make changes to the
  session config; the participant's open tab caches the question.
- **Voice messages need at least a second of audio.** Short taps produce
  empty recordings the transcriber can't read.
- **Don't delete a session you ran the synthesis on** unless you're sure
  — the data dir at `data/<session_id>/` stays on disk so you can re-run
  later, but if you also delete that, the conversations are gone.
- **Sessions, contexts, and workflow customizations are versioned in
  git.** They live as JSON under `config/sessions/`,
  `config/contexts/`, and `config/workflows/`. Commit them if multiple
  admins want to share a setup; gitignore individual files if they
  contain community-sensitive content.

## Architecture

A single Python process (`python -m circle.run`) serves three things
from the facilitator's laptop:

- **Web app** (multi-session) — the admin UI at `/admin` and the
  participant chat at `/s/<session_id>`. All sessions in
  `config/sessions/` are live simultaneously; each gets its own URL.
- **Telegram bot** (single-session, optional) — bound to whichever
  session you select in the admin UI. Switching is a runtime operation,
  no restart needed. If you never bind one, Telegram stays off.
- **Output processors** (synthesis / proposal / revise) — triggered
  from the admin UI as background tasks. Each writes a timestamped
  markdown file under `syntheses/`, `proposals/`, or `revisions/`.

Storage is JSON files on disk:

- `config/sessions/<id>.json` — one per session. Holds the workflow
  type, the participant-facing data (question / document / sub-
  questions), and admin settings (models, depth, context reference).
- `config/contexts/<id>.json` — one per Context Library entry. Reusable
  community-grounding text that sessions reference by id.
- `config/workflows/<type>.json` — optional admin-edited overrides for
  the three big prompt fragments per workflow type. Only created when
  you actually edit them; absence means "use defaults."
- `config/telegram.json` — which session Telegram is currently bound
  to (gitignored, per-environment).
- `data/<session_id>/<participant_id>.json` — one per participant per
  session. The full transcript, extracted points, permission choices.

The only outbound API call is to **Anthropic** for the LLM turns and
the post-conversation processor. Speech-to-text runs locally via
`pywhispercpp` (whisper.cpp) — no audio leaves the laptop.

## Prerequisites

- Python 3.11+
- Node 18+ (for building the web frontend)
- `ffmpeg` on PATH — required to convert browser-recorded WebM/Opus
  voice notes (and Telegram's `.ogg/Opus`) to the 16 kHz mono WAV that
  whisper.cpp expects.
  - macOS: `brew install ffmpeg`
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - Windows: `choco install ffmpeg` or `scoop install ffmpeg`
- An Anthropic API key
- A Telegram bot token from [@BotFather](https://t.me/BotFather) — only
  required if you want the Telegram channel; the web channel works
  without it (but the env var must still be set; can be a placeholder
  if you'll never bind Telegram).

## Setup

```bash
git clone <this repo>
cd Tejido

# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and fill in ANTHROPIC_API_KEY and TELEGRAM_BOT_TOKEN

# Frontend (one-time build; rebuild after pulling frontend changes)
cd web
npm install
npm run build
cd ..
```

That's it. No session YAMLs to edit by hand — sessions are created
through the admin UI.

## Running it

```bash
source .venv/bin/activate
PYTHONPATH=src python -m circle.run
```

That's the whole thing. Visit `http://127.0.0.1:8000/admin` to manage
sessions; participants visit `http://127.0.0.1:8000/s/<session_id>`.

The first launch downloads the whisper model (~1.5 GB for `medium`)
into `models/`. Subsequent launches are instant.

If you want the server reachable from another device on your LAN
(e.g. someone on a phone in the same room): `--host 0.0.0.0`. There's
no auth on the admin UI — see "Privacy" below.

## Participant flow

Same state machine for both web and Telegram channels:

| Phase | What happens |
|---|---|
| `not_started` | Pre-registered (Telegram) or hasn't joined yet (web). |
| `awaiting_consent` | Welcome message + question shown; waiting for "I'm ready". |
| `in_conversation` | Facilitated AI conversation, text or voice. |
| `in_permissions` | 3–5 extracted points, each chosen "By name" / "Anonymous" / "Private". |
| `awaiting_addition` | "Anything to add?" yes/no. |
| `in_addition_permissions` | Granting permission for an addition. |
| `complete` | Done; transcript and permissions persisted. |

## Telegram commands

If Telegram is bound to a session, participants can use:

- `/start` — begin (or, if already started, get a friendly nudge to keep going)
- `/help` — short pointer to the other commands
- `/done` — wrap up early; if it's been less than 5 minutes, the bot confirms
- `/permissions` — re-open the permissions walk-through
- `/restart` — wipe state and start over (requires confirmation)

The web channel exposes the equivalents as buttons in the chat UI.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Covers state-machine transitions, the synthesis permission filter,
workflow validation, session/workflow-override/context/telegram
persistence, and the admin REST surface. ~160 tests.

## Privacy

- Participant conversations are never visible from the session page
  while a participant is mid-conversation. The participants table shows
  phase + duration + turn/word counts only. Transcripts ARE visible
  after the fact via the per-participant detail page — open them only
  after you have the participant's permission, or use them only as
  audit material.
- Audio is transcribed locally via whisper.cpp and never leaves the
  laptop.
- Conversations and permissions are stored in plain JSON under `data/`.
- The only outbound API call is to Anthropic for the AI turns and the
  output processors. The facilitator should communicate this clearly in
  the opening framing.
- **The admin UI has no authentication.** It's intended to run on the
  facilitator's loopback or behind whatever network-level protection
  the deployment provides. Don't expose `/admin` to the public internet.

## Out of scope

This is a prototype focused on the single-laptop, single-facilitator
case. Deliberate non-goals: hosted deployment, multi-admin / RBAC,
admin authentication, persistent participant accounts across sessions,
WhatsApp channel, scoring or sentiment analytics, scaling beyond what
one laptop can comfortably handle.
