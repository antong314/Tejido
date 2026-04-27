Got it — here's the PRD in Markdown.

---

# Product Requirements Document

## AI-Facilitated Group Deliberation Prototype

**Codename:** Circle
**Document version:** 0.1
**Status:** Proof of concept

---

## 1. Product overview

### 1.1 What this is

Circle is a Telegram bot that enables a small group of people (6 participants) to engage in structured private reflection on a shared question before coming together for in-person discussion. Each participant has an individual 20-30 minute facilitated conversation with an AI. After all conversations complete, a synthesis is produced that surfaces shared themes, real disagreements, bridge points between participants, and outlier perspectives. The synthesis becomes the starting point for a group discussion led by a human facilitator.

### 1.2 What problem this solves

Groups need to build shared understanding on substantive questions. Two common approaches fail at even small scales:

- **Group discussion** (in-person or over messaging platforms like WhatsApp) tends to be dominated by the loudest voices, produces heated low-quality exchanges, and causes most participants to disengage rather than contribute.
- **Surveys** flatten complex perspectives into checkboxes, treat all participants as equally engaged, and produce data that doesn't capture underlying values or willingness to compromise.

Neither approach does what a well-facilitated circle of 10 or fewer does: gives each person space to articulate their real perspective, surfaces both agreements and disagreements honestly, and creates a basis for collective sense-making. Circle is an experiment in whether AI can act as a faithful amplifier of individual voices while preserving the primacy of the in-person group experience.

### 1.3 Who this is for

The initial users are a pre-existing group of 6 people who gather weekly for 2 hours. They are motivated participants in a small community context, comfortable with Telegram and with one another. This is not designed for broad consumer use. It is designed to test the core facilitation experience in a low-risk, high-trust setting before any consideration of broader deployment.

### 1.4 What success looks like

The prototype succeeds if, after one session:

1. Participants report that the individual AI conversation surfaced thinking they wouldn't have expressed in a normal group discussion.
2. Participants feel the synthesis faithfully represents what they said, without misattribution or misrepresentation.
3. The group's in-person discussion after the synthesis reveal feels qualitatively different from — and ideally better than — their normal discussion of similar questions.
4. The matchmaker moment (bridging participants who share an underlying concern) lands as meaningful for at least some participants.
5. No participant feels surveilled, flattened, or reduced by the experience.

The prototype explicitly does not need to demonstrate scalability, commercial viability, or broad applicability. It needs to produce a clear signal on whether this approach is worth pursuing further.

---

## 2. Experience design

### 2.1 The full participant journey

**Before the session (1-2 days prior)**

Participants receive a short briefing message, either in person, via a group chat, or through Telegram directly from the bot. The briefing explains:

- What the session will involve (individual AI conversation, group discussion, reflection)
- The question(s) that will be explored
- How their words will be handled (private conversation with AI, synthesis shared with the group, explicit permission step before anything is attributed)
- Technical prep (install Telegram if needed, have earbuds available)

**Session start (0:00 – 0:15)**

The group gathers in person. The human facilitator opens with a brief framing of the experiment, establishes trust and privacy norms, and introduces the question(s). Each participant does a one-sentence check-in in the circle. The facilitator then asks everyone to open Telegram and begin a conversation with the bot by sending `/start`.

**Individual conversation phase (0:15 – 0:50)**

Participants spread out to private pods (different rooms, corners, outside) with their phones and earbuds. Each person has a 20-30 minute individual conversation with the bot. Participants can choose voice or text at any point — voice messages are transcribed and responded to in text; text works end-to-end as chat.

The conversation follows a natural arc: opening reaction, deeper exploration of what they said, tradeoffs, edge cases, reflection on uncertainty. The AI does not lead toward any conclusion, share its own opinions, or inform — it draws out the participant's thinking.

The conversation ends with a **permissions phase**, in which the AI surfaces the 3-5 main points the participant made during the conversation, and for each one asks the participant to choose: attributed (shared with name), anonymous (shared without name), or private (not shared at all). This is done via Telegram inline keyboard buttons — one tap per permission.

**Synthesis generation (0:45 – 0:55)**

As participants finish, transcripts plus permissions are compiled. The human facilitator triggers synthesis generation (a separate process) that reads all 6 transcripts and produces a one-page structured document covering: shared themes, real divergences, bridge points, outlier voices, and questions for group discussion. The facilitator reviews the synthesis for accuracy before Phase 2.

**Group reveal and discussion (0:55 – 1:35)**

The group reconvenes in the physical circle. The facilitator walks through the synthesis out loud, using direct quotes from the transcripts (respecting permissions). The structure is: shared themes first (recognition, settling), then real disagreements named precisely (without attempting to resolve them), then bridge moments where two participants are explicitly connected, then outlier voices given their space. After the walkthrough, the group discusses naturally using the synthesis as a starting point.

**Process reflection (1:35 – 2:00)**

The final 25 minutes shift into meta-discussion about the experiment itself. The group reflects on what the AI conversation surfaced that normal discussion wouldn't, whether the synthesis felt faithful, whether the bridge moments landed, and whether they'd want to use this for which kinds of questions in the future.

### 2.2 Participant mental model

A participant should experience Circle as three distinct moments:

1. **A private thinking partner** — the AI conversation feels like a thoughtful friend helping them articulate what they actually think, not an interview, not a survey, not a chatbot.
2. **Recognition and connection** — hearing their own words and their neighbors' words surfaced in the group creates a felt sense that they were heard and that others were heard too.
3. **Agency over their own voice** — they control what becomes public, by name or anonymously, and nothing leaves their conversation without explicit consent.

The AI should never feel like a gatekeeper, an expert, an authority, or a data collector. It is a tool the group is using to hear itself better.

### 2.3 Facilitator mental model

The human facilitator owns the session. The bot is an instrument they deploy during specific phases. The facilitator:

- Runs the opening and closing circles
- Monitors conversation progress during the individual phase (via dashboard — see section 4.6)
- Reviews and sanity-checks the synthesis before presenting it
- Walks the group through the synthesis, reading it aloud rather than distributing it
- Leads the group discussion and the meta-reflection

The facilitator is expected to exercise judgment. If the synthesis contains something that would misrepresent a participant, they edit or drop it. If a bridge feels forced, they don't present it. The AI produces raw material; the facilitator curates its presentation.

---

## 3. Core conversational behaviors

### 3.1 Facilitator AI behavior

The facilitator AI conducts the individual conversation. Its behavior is governed by the following intent, expressed in the actual system prompt below.

**Primary intent:** Help the participant articulate what they actually think and feel about the question, including parts they haven't fully worked out. Draw out, don't add.

**Key behaviors:**

- Opens with an invitation to gut reaction, not a structured question set
- Follows the participant's thread rather than running a checklist
- Probes for the layer beneath stated positions ("what's driving that for you?")
- Tests tradeoffs gently ("if honoring X meant giving up Y, how would you weigh that?")
- Presents counterpositions fairly without advocating for them
- Welcomes uncertainty and changes of mind
- Reflects back periodically and invites correction
- Does not share its own views, even when asked
- Does not provide information unless explicitly requested
- Does not use affirmations that stop thinking ("great point!")
- Does not interpret or diagnose the participant's values in therapy-speak
- Does not push toward resolution

**System prompt for the facilitator AI:**

```
You are a thoughtful facilitator helping someone think through a question that matters to their community. You are NOT an expert, NOT an advocate, and NOT trying to inform or persuade. Your only job is to help this person articulate what they actually think and feel — including the parts they haven't fully worked out yet.

THE QUESTION BEING EXPLORED:
{QUESTION}

CONTEXT (share only if asked):
{CONTEXT}

YOUR APPROACH:

Start open. Don't telegraph any position. Begin with something like: "Before we get into specifics, what's your gut reaction when you think about this question? What comes up for you?"

Follow their thread. If they mention a concern, explore it. If they mention a hope, explore it. Don't have a checklist you're running through — have a genuine curiosity about their specific perspective.

Probe for the layer beneath. When someone says "I want X," ask what X would look like concretely, and what's driving that for them. The stated position is usually a compression of something richer. Your job is to decompress it.

Examples of good probing questions:
- "When you say [their word], what does that look like concretely for you?"
- "What's underneath that for you? What would it mean if we didn't do that?"
- "Can you give me an example of a time this mattered to you?"
- "What are you afraid might happen if we go the other way?"

Surface tradeoffs without leading. Once you have a sense of their position, test its edges gently: "If honoring what you just said meant giving up [something else they mentioned caring about], how would you weigh that?" You're not trying to trap them — you're helping them find where their real priorities lie.

Test edge cases and counterpositions. "Some people might say [alternative view] — how do you respond to that?" This isn't debate. It's giving them a chance to articulate their reasoning against a real alternative. Present the counterposition fairly.

Make space for uncertainty. Actively invite it: "Is there anything you're genuinely unsure about here? Anything you've changed your mind on, even mid-conversation?" People often have the most to say about the parts they haven't resolved. Welcome that.

Reflect back, but carefully. Periodically summarize what you're hearing — "so it sounds like your top priority is X, and you're more flexible on Y, is that right?" Let them correct you. The correction is often more valuable than the agreement.

TONE:

Warm but not performative. Curious but not prying. You are genuinely interested in this specific person's perspective. You have no agenda of your own on the substantive question. You are not trying to reach consensus, build agreement, or move them toward any conclusion.

Don't be sycophantic. Don't say "great point!" or "that's so interesting!" Just stay with them and keep going deeper.

Match their energy. If they're brief, don't force them to be verbose. If they're expansive, give them room. If they're uncertain, slow down with them. If they're fiery about something, let them be fiery — don't cool them off.

WHAT NOT TO DO:

Do not share your own opinion, even if asked. If pressed, redirect: "My job tonight is to help you articulate what you think, not to add my own view to the mix. What draws you to ask?"

Do not provide information, research, or expert framing unless explicitly requested, and even then only briefly. You are not a Wikipedia article. Their perspective is what matters here.

Do not push toward resolution. Some people will finish knowing exactly what they think. Others will finish more confused than they started. Both are valid outcomes of honest thinking.

Do not use language that suggests you're collecting data. No "thanks for sharing" or "I've noted that." Stay in the register of conversation, not interview.

Do not interpret or diagnose. Don't say "it sounds like you have a deep value around autonomy." Let them name their own values in their own words.

STRUCTURE:

Aim for 20-30 minutes of conversation. No hard time limit, but gently move through phases:
- Opening (5 min): their initial reaction and what's alive for them
- Depth (10-15 min): the underlying values, concerns, and specifics
- Edges (5-10 min): tradeoffs, edge cases, counterpositions
- Integration (5 min): reflection, uncertainty, what they're left with

When you sense the conversation has reached a natural completion — the participant has articulated their perspective with depth, explored tradeoffs, and reflected on their uncertainty — output the exact token [READY_FOR_PERMISSIONS] on its own line at the end of your message, followed by a brief closing sentence. The system will then transition to the permissions phase.

You may also output [READY_FOR_PERMISSIONS] if the participant clearly wants to wrap up, or if they've plateaued and further probing is becoming unproductive.
```

**Configuration parameters for the facilitator AI:**

- Model: Claude Sonnet 4.5 (`claude-sonnet-4-5`)
- Temperature: 0.7 (warm but coherent)
- Max tokens per turn: 500 (prevents the AI from lecturing)
- Context window: full conversation history

### 3.2 Permissions AI behavior

After the facilitator AI signals readiness, a separate process extracts the main points the participant made and walks them through the permissions phase.

**Primary intent:** Give the participant clear, specific control over which parts of their conversation are shared with the group and how.

**Key behaviors:**

- Extracts 3-5 discrete points from the conversation, each expressed as a short sentence in the participant's own language where possible
- Presents each point one at a time via Telegram, with three inline keyboard buttons: "By name", "Anonymous", "Private"
- Does not interpret or reframe — uses the participant's language
- Allows the participant to add anything that wasn't captured
- Confirms the set of permissions at the end before closing

**System prompt for the permissions extraction:**

```
You are reviewing a transcript of a facilitated conversation. Your job is to identify the 3-5 main points the participant made — substantive positions, values, concerns, or proposals that they expressed.

TRANSCRIPT:
{TRANSCRIPT}

Extract between 3 and 5 points. Each point should:
- Be expressed in one sentence
- Use the participant's own language where possible (you can paraphrase for clarity, but preserve their voice)
- Capture something substantive — a position, a value, a concern, a tradeoff, a proposal
- Be distinct from the other points (no overlap)

Do NOT include:
- Small talk or meta-comments about the conversation
- Things they explicitly retracted or walked back
- Your interpretations of their underlying values in abstract terms
- Generic framings ("they value community")

Output a JSON array of strings, one per point. Example:
[
  "I think hot lunch matters more than ingredient quality — kids need to eat something filling.",
  "I'd pay more for organic if the school could guarantee it actually ended up on kids' plates.",
  "I'm worried about kids with allergies being excluded from shared meals."
]

Output ONLY the JSON array, no other text.
```

**Permissions UI flow:**

1. Bot sends: "Thanks for that conversation. Before we wrap up, I want to check with you about what gets shared with the group. I'll walk through 4 things you said, and for each one, you can choose how it gets shared — by name, anonymously, or not at all."
2. For each point, bot sends the point as a message, followed by three inline buttons
3. Bot records each choice silently ("✓")
4. After all points, bot sends: "Is there anything else you'd like to add that didn't come up? Anything the group should hear?"
5. If they respond, record the addition (with its own permissions pass)
6. Bot closes: "That's it. Thank you. We'll come back together in the circle when everyone has finished."

### 3.3 Synthesis AI behavior

After all participants have completed their conversations and permissions, the synthesis AI produces the document that the facilitator will walk through with the group.

**Primary intent:** Surface what the group said — shared themes, real disagreements, bridges, outliers, and questions — without smoothing, without hallucinating, without recommending.

**Key behaviors:**

- Respects permissions strictly; anonymizes where required; omits entirely where marked private
- Uses direct quotes generously, with attribution per permissions
- Classifies disagreements as values/factual/framing to focus later discussion
- Flags uncertain bridges rather than manufacturing consensus
- Writes for spoken delivery (the facilitator will read it aloud)
- Does not produce recommendations, executive summaries, or conclusions

**System prompt for the synthesis AI:**

```
You are helping a facilitator prepare a structured reflection for a group of six people who just completed individual AI-facilitated conversations about the same question. The group is about to reconvene in person to discuss. Your job is to produce a one-page synthesis document that the facilitator will walk through with the group.

THE QUESTION THEY EXPLORED:
{QUESTION}

PARTICIPANT PERMISSIONS:
Each transcript includes a permissions section at the end specifying, for each main point the participant made, whether it can be attributed by name, shared anonymously, or must stay private. RESPECT THESE STRICTLY. When in doubt, anonymize. If something was marked private, do not include it at all, even in aggregate form.

THE SIX TRANSCRIPTS:
{TRANSCRIPTS}

YOUR OUTPUT — PRODUCE THESE FIVE SECTIONS:

1. SHARED THEMES (aim for 3-5)

Identify themes that appeared across multiple conversations. For each theme:
- State the theme in one sentence, using the participants' own language where possible
- Include 2-3 short verbatim quotes from different participants (respecting permissions)
- Note roughly how many of the six touched on this theme

A theme is not a position everyone holds — it's a concern, value, or frame that showed up in multiple conversations. Two people can share a theme while disagreeing about what to do about it.

2. REAL DIVERGENCES (aim for 2-3)

Identify places where participants genuinely disagree. For each divergence:
- State the disagreement precisely and fairly — not "some want X and others want Y" but the actual texture of the disagreement
- Attribute positions per permissions (by name if allowed, anonymously otherwise)
- Classify the type: is this a VALUES disagreement (different priorities), a FACTUAL disagreement (different beliefs about what's true or what would work), or a FRAMING mismatch (they're actually responding to different questions)?
- Include short verbatim quotes that capture each side

Be honest about disagreement. Do not smooth it over. The group needs to see it clearly to discuss it productively.

3. BRIDGES (aim for 1-2)

Identify pairs or small groups of participants who expressed structurally similar things using different words, or who came at the same underlying value from different angles. For each bridge:
- Name the pair (per permissions)
- Quote both participants
- Articulate what you think they have in common beneath the surface difference

Be careful here. Do not manufacture bridges that aren't really there. If the similarity is genuine, it's powerful. If it's stretched, it will feel like the AI is trying to force agreement. If you're not sure, flag it as "possible bridge" and let the group decide.

4. OUTLIER VOICES (aim for 1-2)

Identify something one participant said that no one else raised, which seems worth the group hearing. This might be:
- A perspective that the rest of the group missed entirely
- A reframe of the question that no one else considered
- A concern or hope that is unique but important
- A creative proposal that hasn't been discussed

Attribute per permissions. Quote directly.

Do not include something here just because it's unique — include it because it's unique AND substantive.

5. QUESTIONS THE GROUP SHOULD DISCUSS

Based on what came up across the six conversations, suggest 2-3 questions the group could productively discuss together. These should be questions that:
- Surfaced in multiple conversations but weren't fully resolved
- Represent the real work the group needs to do together
- Cannot be answered individually — they need collective deliberation

Frame them as genuine open questions, not leading questions.

OUTPUT FORMAT:

Plain text, clearly structured with the five section headers. Keep total length to roughly one page (500-800 words). The facilitator will read this aloud or paraphrase it in the circle, so write for spoken delivery: clear, not overly dense, with natural pauses.

Use direct quotes generously but keep them short (one or two sentences each). The quotes are what will land for participants — they'll recognize themselves and each other.

WHAT NOT TO DO:

Do not produce an executive summary or a recommendation. Your job is to surface what the group said, not to tell them what to do with it.

Do not soften disagreements to make the output feel harmonious. Honest disagreement is the most valuable thing the group can see.

Do not include anything marked private. Do not attribute anything anonymized. When in doubt, leave it out.

Do not use therapy-speak or abstract values language ("the group values connection"). Use the participants' actual words and specific claims.

Do not fabricate. If something isn't in the transcripts, it's not in the synthesis. If you're uncertain whether something qualifies as a shared theme, flag that uncertainty.
```

**Configuration parameters for the synthesis AI:**

- Model: Claude Sonnet 4.5
- Temperature: 0.3 (lower — we want faithfulness, not creativity)
- Max tokens: 2000 (enough for a full one-page synthesis)

---

## 4. System architecture

### 4.1 High-level architecture

```
┌─────────────────┐       ┌──────────────────┐       ┌─────────────────┐
│   Telegram      │◄─────►│   Bot Server     │◄─────►│   Anthropic     │
│   (6 users)     │       │   (Python)       │       │   API (Claude)  │
└─────────────────┘       └──────────────────┘       └─────────────────┘
                                   │
                                   │ voice msgs
                                   ▼
                          ┌──────────────────┐
                          │   OpenAI API     │
                          │   (Whisper)      │
                          └──────────────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │  Local storage   │
                          │  (JSON files)    │
                          └──────────────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │ Synthesis script │
                          │ (invoked by      │
                          │  facilitator)    │
                          └──────────────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │ Facilitator      │
                          │ dashboard        │
                          │ (terminal)       │
                          └──────────────────┘
```

### 4.2 Components

**Bot server.** A persistent process that handles all Telegram interactions. Maintains per-participant state, routes messages to the appropriate handler based on conversation phase, calls the Anthropic API for facilitator responses, calls OpenAI Whisper for voice transcription, and writes transcripts and permissions to disk as they evolve.

**Storage layer.** One JSON file per participant, keyed by Telegram user ID. Contains: participant identifier, current phase (not started / in conversation / permissions / complete), full conversation history with timestamps, list of extracted points with permissions decisions, and any metadata (start time, end time, language preference if set). For a 6-person prototype, file system is sufficient; no database needed.

**Synthesis script.** A standalone script invoked manually by the facilitator during the break. Reads all completed participant files, assembles the synthesis prompt, calls the Anthropic API, writes output to a markdown file for the facilitator to review. Not part of the bot server process.

**Facilitator dashboard.** A terminal-based view (simple script refreshed on demand, or a lightweight web page) that shows the facilitator, in real time, which participants are in which phase and roughly how long each has been in their current phase. Critically, the dashboard does not show conversation content — the facilitator cannot read participants' private conversations. Only phase and duration.

### 4.3 Participant state machine

Each participant moves through these states:

- **`not_started`** — bot knows the participant's Telegram handle (pre-registered by facilitator) but they haven't sent `/start` yet
- **`awaiting_consent`** — participant has sent `/start`, bot has sent welcome message and explained what happens, waiting for participant to confirm they're ready
- **`in_conversation`** — active facilitated conversation with the AI
- **`in_permissions`** — conversation complete, walking through the extracted points with permission choices
- **`awaiting_addition`** — asked if there's anything else to add
- **`in_addition_permissions`** — if they added something, granting permission for that addition
- **`complete`** — all permissions granted, final transcript + permissions written, participant thanked

Transitions:

- `not_started` → `awaiting_consent`: participant sends `/start`
- `awaiting_consent` → `in_conversation`: participant confirms readiness
- `in_conversation` → `in_permissions`: either the AI outputs `[READY_FOR_PERMISSIONS]` or the participant types `/done`
- `in_permissions` → `awaiting_addition`: all extracted points have permissions granted
- `awaiting_addition` → `in_addition_permissions` or `complete`: depending on whether they add something
- `in_addition_permissions` → `complete`: addition permission granted

### 4.4 Message handling flow

**For text messages during `in_conversation`:**
1. Receive message from Telegram
2. Load participant state and conversation history
3. Append user message to history
4. Call Anthropic API with facilitator system prompt + conversation history
5. Parse response; check for `[READY_FOR_PERMISSIONS]` token
6. Send response to participant (stripped of token if present)
7. Save updated state
8. If token present, transition to permissions phase after a short delay

**For voice messages during `in_conversation`:**
1. Receive voice message from Telegram; download .ogg file
2. Call OpenAI Whisper API for transcription (auto-detect language)
3. From this point, treat as text message (step 2 above), but mark the message in the transcript as originating from voice

**For button taps during `in_permissions`:**
1. Receive callback query from Telegram (contains the permission choice and the point index)
2. Record the choice in the participant's permissions list
3. Send confirmation ("✓") by editing the previous message to remove buttons and append the choice
4. If more points remain, send the next one
5. If all points handled, transition to `awaiting_addition`

### 4.5 Permissions data model

Each participant's final output contains:

```json
{
  "participant_id": "telegram_user_id",
  "participant_name": "Ana",
  "session_id": "session_20260426",
  "question": "How should we make decisions about shared land use?",
  "transcript": [
    {"role": "user", "content": "...", "timestamp": "...", "via": "voice|text"},
    {"role": "assistant", "content": "...", "timestamp": "..."}
  ],
  "extracted_points": [
    {
      "point": "I think we need to hear from longer-term residents before short-term ones.",
      "permission": "attributed|anonymous|private",
      "index": 0
    }
  ],
  "additions": [
    {
      "content": "...",
      "permission": "attributed|anonymous|private"
    }
  ],
  "status": "complete",
  "started_at": "...",
  "completed_at": "..."
}
```

Critically: points marked `private` must be retained in the participant's file (so they can see what they said) but must be filtered out before the transcripts are passed to the synthesis AI. The filtering happens at synthesis time, not at storage time — the participant's own record is preserved in full.

### 4.6 Facilitator dashboard

The dashboard shows, at any moment:

| Participant | Phase              | Duration in phase | Total time |
|-------------|--------------------|--------------------|------------|
| Ana         | in_conversation    | 14 min             | 14 min     |
| Boris       | in_permissions     | 2 min              | 23 min     |
| Carolina    | complete           | —                  | 27 min     |
| Diego       | in_conversation    | 8 min              | 8 min      |
| Elena       | awaiting_consent   | 1 min              | 1 min      |
| Felipe      | not_started        | —                  | —          |

No conversation content is displayed. The facilitator uses this to pace the session: if 5 of 6 are complete and one is deep in conversation, they know to give that person space rather than calling time early.

### 4.7 Synthesis generation flow

Invoked by the facilitator (command-line or button press) when they judge enough participants have completed:

1. Load all participant files with status `complete`
2. For each participant, filter out any conversation turns or extracted points marked `private`
3. Assemble the synthesis prompt with the question and the filtered transcripts
4. Call Anthropic API with synthesis system prompt
5. Write output to `synthesis_YYYYMMDD.md` in a known location
6. Display success message with file path

The facilitator opens this file, reviews it, edits if needed, and uses it to lead Phase 2.

### 4.8 Error handling and edge cases

The prototype needs to handle these gracefully without crashing or losing state:

- **Participant stops responding mid-conversation.** The bot waits. State is preserved on disk. If they come back later (even in a future session), their conversation can resume. The facilitator dashboard shows them stuck in their current phase with an increasing duration.
- **Participant sends `/start` twice.** Bot responds with a gentle message acknowledging they've already begun and asks if they want to restart (requires explicit confirmation) or continue.
- **Voice transcription fails.** Bot sends a message explaining the transcription failed and asks the participant to try again or type the message.
- **Anthropic API failure.** Bot retries with backoff. If still failing, sends a message explaining there was a technical issue and the facilitator will help.
- **Participant wants to edit a permission after granting it.** They can type `/permissions` to re-open their permissions. The bot walks through all their extracted points again, showing the current choice, and allows changes. Must be allowed before `complete` phase.
- **Participant types `/done` very early.** Bot confirms: "Are you sure? We've only been talking for X minutes." If they confirm, proceed to permissions.
- **Two participants finish at very different times.** Synthesis only runs when facilitator invokes it. Late finishers can be included by re-running synthesis, or excluded with explicit facilitator decision.

---

## 5. Non-functional requirements

### 5.1 Privacy

- Participant conversations are never viewable by the facilitator or anyone else during the session. Only the participant sees their own conversation.
- After the session, conversations are stored locally on the facilitator's machine. They are not uploaded to any cloud service beyond the API calls required (Anthropic, OpenAI).
- API calls to Anthropic and OpenAI are subject to those providers' data handling policies. The PRD assumes the facilitator communicates this clearly in the opening framing.
- Permissions are the source of truth for what can be shared. The synthesis pipeline must filter by permissions before any aggregate output is generated.
- No analytics, telemetry, or third-party tracking.

### 5.2 Languages

The prototype targets Spanish and English. Voice transcription auto-detects. The facilitator and synthesis AI should produce output in the language of the transcripts — if the majority of conversations happened in Spanish, the synthesis is in Spanish. If mixed, synthesis should preserve quotes in their original language.

### 5.3 Performance

- AI response latency should target under 5 seconds per turn under normal conditions. Longer is acceptable but should be communicated (a "typing" indicator in Telegram).
- Voice transcription typically completes in under 10 seconds for messages under 2 minutes.
- Synthesis generation may take 30-90 seconds; this is acceptable because the facilitator invokes it during the break.

### 5.4 Reliability

- Participant state must be persisted after every message, so an unexpected bot restart doesn't lose conversation progress.
- The bot should be runnable on the facilitator's laptop during the session. No external infrastructure dependencies beyond the two APIs.
- Graceful degradation: if the synthesis fails, the session can still proceed with the facilitator reading transcripts themselves; the individual conversations are the primary value.

### 5.5 Accessibility

- Voice input supported for participants who prefer speaking over typing, or who have difficulty typing on mobile.
- Text-only path must be fully functional for participants who prefer text or are in environments where voice isn't practical.
- Inline keyboard buttons are large enough to tap easily on a phone.

---

## 6. Out of scope for this prototype

The following are explicitly not included and should not be built:

- Any user account system beyond Telegram's built-in identity
- Support for more than 6 participants in a single session
- Any administrative UI for managing questions, sessions, or participants beyond what the facilitator sets up manually in config
- Multi-session continuity (e.g., picking up a conversation from last week)
- Asynchronous participation (everyone participates in the same 35-minute window)
- Any deployment infrastructure — the bot runs on the facilitator's machine
- WhatsApp support (Telegram only for this prototype)
- Automated matchmaker follow-up (the matchmaker moment is surfaced in synthesis; any actual introductions between participants happen in the group discussion, not via the bot)
- Any scoring, rating, or voting mechanism
- Persistent identity across sessions or groups
- Integration with any external systems

---

## 7. Configuration for a specific session

The facilitator configures each session via a config file or environment variables before running the bot. The configuration includes:

- **Question(s) to be explored** — the exact question text passed to the facilitator AI
- **Context** — optional background information the AI can share if asked (kept minimal)
- **Participant list** — Telegram handles or user IDs for the 6 participants, with their display names
- **Anthropic API key**
- **OpenAI API key** (for Whisper)
- **Telegram bot token**
- **Session identifier** — used in file naming
- **Language preference** (optional) — if known in advance, can set "es" or "en"; otherwise auto-detect

---

## 8. Success signals to measure

The prototype is not instrumented with analytics. Success will be evaluated through:

1. **Direct observation during the session** — the facilitator watching participants during individual conversations and the group reveal
2. **The Phase 3 reflection discussion** — captured via notes or recording (with consent), treated as primary research output
3. **Transcript review after the session** — the facilitator reading through transcripts to evaluate: did the AI facilitation feel faithful? Were there missed opportunities to probe? Did any conversations feel hollow or leading?
4. **Follow-up with participants 1-3 days later** — short optional survey or conversation asking whether the experience stayed with them and whether they'd want to do it again

The key signals to watch for:

- Participants saying something in the AI conversation they would not have said in the group
- Participants recognizing themselves in the synthesis with a sense of "yes, that's what I said"
- Real disagreements being named and explored rather than avoided
- At least one bridge moment that produces a visible "oh" in the group
- The group discussion in Phase 2 feeling qualitatively different from their normal discussions

Failure signals to watch for:

- Participants feeling interrogated, extracted from, or flattened
- The synthesis feeling bland, consensus-forced, or missing the real substance
- The group discussion feeling like a debrief of the AI's output rather than a living conversation
- Any participant feeling misattributed or having their words used without permission

---

## 9. Open design questions for the coding agent to flag, not resolve

- The exact threshold for when the facilitator AI outputs `[READY_FOR_PERMISSIONS]` is judgment-based and will require tuning. The prototype should make it easy to adjust by editing the prompt.
- Whether the permissions step should happen mid-conversation (point-by-point as things come up) or all at the end is an open design question. The PRD specifies end-of-conversation for simplicity; a future version could experiment with in-flow permissioning.
- Voice reply from the bot (text-to-speech) is possible but not specified. If trivial to add with a library like ElevenLabs or OpenAI TTS, it could be a nice-to-have; if it adds complexity, skip it.
- Whether to include a brief "what you said" summary at the very end of the permissions phase (before the final thank-you) to give participants closure. Could be a 2-3 sentence summary generated by a lightweight AI call. Not specified in the core flow but worth considering.

---

## 10. Appendix: example session configuration

Example `session_config.yaml`:

```yaml
session_id: "valle_machuca_2026_04_26"
question: "What should guide our decisions about how new members join our community?"
context: |
  Our community currently has 12 founding families. We've had informal conversations
  about membership but no written policy. Some new families have expressed interest
  in joining, and we need to decide how to approach this.
participants:
  - handle: "@anamarquez"
    display_name: "Ana"
  - handle: "@boris_k"
    display_name: "Boris"
  # ... etc
language: "auto"
facilitator_model: "claude-sonnet-4-5"
synthesis_model: "claude-sonnet-4-5"
```

---
