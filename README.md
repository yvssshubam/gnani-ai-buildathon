# Surgeline

**When every line is busy, Surgeline picks up.**

A phone line that answers flood rescue calls when every human operator is busy. It talks to
the caller in their own language, collects what rescuers need (where they are, how many
people, who is vulnerable, how high the water is), reads it back for confirmation and turns
the call into a prioritised rescue ticket. A control-room dashboard shows the ticket live, and
an operator sends a rescue team.

Built as a solo entry for Gnani AI's Great Indian AI Internship Challenge.
It is a **prototype tested on synthetic and test calls**, not a deployed service.

---

## The problem

In major floods, the channels people use to ask for help fail at the moment they're needed most:

- **Helplines can't take enough calls at once.** In a surge, callers can't get through, and
  requests go unanswered.
- **Requests move to social media**, where they are scattered, duplicated and hard to act on.
  Volunteer teams have had to handle up to 2,000 requests a day.
- **Details get lost between people.** A request passes from the caller to an operator to a
  control room to a rescue team, and each handover can drop or change details.
- **Callers don't all speak the operator's language**, and many mix languages
  ("hum second floor par hain, water knee tak hai").

Surgeline is meant to **add capacity next to human operators**, not replace them: the AI
takes calls only when no person is free, and hands over to a human whenever the call needs one.

---

## How a call works

```
caller speaks ──► speech-to-text (Gnani Prisma) ──► transcript
                                                    │
         short answer ("4", "haan", "600042")  ◄────┤────► longer sentence
         understood by plain code, no LLM            │     one LLM call extracts the facts
                                                    │     and says which language the words are in
                                                    ▼
          language decided (Prisma's tag + the script + the LLM) ──► reply language
                                                    │
                         ticket updated ──► priority set by FIXED RULES (not the LLM)
                                                    │
                     code picks the next step: ask what's missing / read back / close / hand to a human
                                                    │
                         reply built from reviewed lines in the caller's language
                                                    ▼
                                 text-to-speech (Gnani Timbre) ──► caller
```

**Ask order:** immediate danger → area → street / house → floor → people → vulnerable people → water level.
Anything the caller already said is never asked again. Each question gets at most two tries
(the second is simpler) and then the call moves on.

### Design rules

- **The LLM never decides priority.** Fixed rules in `app/priority.py` do:

  | Priority | Meaning | Examples |
  |---|---|---|
  | P0 | Life in danger now: a human is alerted | water at chest level, medical emergency, injury, unsafe building, rising water with vulnerable people |
  | P1 | Serious, or not known yet | waist-deep water, vulnerable people, trapped, water rising, danger not known |
  | P2 | Needs rescue, stable | rescue needed, water present, no vulnerable people reported |
  | P3 | Relief or information only | food, water, medicine |

- **What the caller hears is fixed and reviewed** (`app/phrases.py`). The LLM can add two
  things, and code checks both before they are spoken:
  - a short acknowledgement of what the caller said, and
  - a one-sentence reply when the caller goes off-script ("I only know the PIN code, is that
    ok?" → "Yes, tell me the PIN code."), at most 3 times a call.

  Anything too long, in the wrong language or script, or sounding like a promise ("the boat
  is coming in 10 minutes") is thrown away, and the fixed line is used.
- **The call never loops.** If the caller gives nothing new for 3 turns in a row (2 if they
  are panicking), repeats the same question, or says "I don't know" to everything, the call
  is handed to a human officer with the ticket number.
- **It handles the moments a script misses:**
  - **"What does floor mean?"** The same question in simpler words, not echoed back.
  - **"Shall I tell you?"** "Yes, tell me," and the next answer still counts. Caught by rule
    in all four languages.
  - **"I don't know where I am."** No street or house-number question. It asks once what they
    can see nearby, then moves on and flags the ticket for a callback.
  - **"I'm going to die."** Treated as panic: a calming line first, then simple yes/no questions.
- **A "no" at the read-back is taken seriously.** "No, that's wrong" with no new details makes
  the agent ask what's wrong. It never repeats the same read-back word for word.
- **Speech recognition makes mistakes, so the ticket only records what's clear.** The LLM reads
  sound-alike errors in context, but a guessed injury, number or place stays off the ticket,
  so the agent asks. "Our house" or "मेरा घर" is never saved as a building or street name.
- **Tickets are in English, with the caller's own words kept.** Street names given in Hindi,
  Telugu or Tamil script are converted to English letters for responders (`नेहरू स्ट्रीट` →
  `Nehru Street`), and the original stays for the read-back. A 6-digit PIN code counts as
  area-level location and is read back digit by digit.
- **Tickets that need a human say so.** If the location is only known to area level, the call
  drops mid-way, or a stable P2 case has water, the ticket gets a follow-up reason
  (for example, re-check the water level in 30 minutes).

---

## Languages

| Caller speaks or types | Status |
|---|---|
| English, Hindi, Telugu, Tamil | Tested by voice and in text mode |
| Switching language mid-call (Hindi → Telugu → Hindi) | Tested by voice |
| Mixed with English ("हम second floor पर हैं", "Church Road, first floor") | Tested |
| Typed in English letters: Hinglish ("hum ghar mein hain"), Telugu, Tamil | Tested |
| Other Indian languages in their own script | Detected; the reply falls back to Hindi and the ticket is flagged "interpreter needed" |
| Other Indian languages in English letters | Not supported yet (read as English) |

**How the call's language is decided.** Each caller turn is judged from three sources:
- Prisma's language tag,
- the script of the transcript, and
- the LLM reading the words. Hindi that speech-to-text wrote in Tamil letters is still Hindi.

A full sentence (4+ words, or 12+ letters, so short Telugu and Tamil sentences count)
switches the call at once when Prisma and the LLM agree. Otherwise the new language needs
two turns in a row. So one English "ok" doesn't flip the conversation, and neither does one
wrong guess. A phone handed to a neighbour who speaks another language does switch it.

---

## Voice layer (Gnani)

- **Speech to text:** Gnani Prisma v3.0 (`/stt/v3`) in code-mix mode, one request per caller
  turn. Every request is the same, whatever language the call is in:
  - the language hints in a fixed order (`STT_LANGUAGES`),
  - up to 200 place names in English spelling, and
  - the agent's last question in English as context.

  Shaping requests by the call's language made one wrong guess stick, so they are neutral.
- **Text to speech:** Gnani Timbre v2.5 with a soft agent voice per language (Yashvi for
  Hindi, Shlok for English, Lehara for Telugu, Noopur for Tamil). Audio is cached on disk, and
  fixed lines are pre-generated so they play instantly.
- **Retries:** rate limits and server errors are retried with backoff. A failed LLM extract is
  retried once. If it still fails, the turn falls back safely.
- **Browser recorder:** stops on silence and sends 16 kHz WAV per turn. It can't get stuck on
  "Listening":
  - it ignores the agent's echo for a moment after the agent stops speaking,
  - the level that counts as speech is capped below a normal voice,
  - the noise level comes down as soon as the room is quiet, and
  - **Done speaking** sends the turn even if speech was never detected.

## Control room

- **Dashboard** (React 18, Vite, MapLibre with free OpenFreeMap tiles):
  - a queue sorted by priority, with live calls marked,
  - a map with ticket pins, flood areas, teams and routes,
  - an ankle-to-neck depth gauge,
  - ticket detail with suggested teams, travel distance and assign,
  - a live call panel with **Take over**, and
  - a rescuer page (`#/rescuer/:id`) for the team in the field.
- **Dispatch:** 3 boats, 1 fire and rescue, 1 medical team, each with position, seats, and
  deep-water and medical ability. Includes assignment, field status updates, shifts, and SMS
  text for the team.
- **Answer it yourself:** an operator takes a call directly; the AI listens, fills the ticket
  and takes notes.
- **AI note-taker:** runs in the background after each turn and never slows the call. It
  writes a summary and an English translation of every line. **Check my notes** compares the
  operator's notes with the transcript, quoting the caller's exact words and the time.
- **Call screen** (`#/call`): talk to the agent with your microphone, or run a simulated
  caller. The simulated caller can be a scripted scenario or an LLM role-play, with its own
  Gnani voice, and its audio goes through real speech to text.

---

## Status

| Phase | What | State |
|---|---|---|
| 1 | Call engine: extraction, triage, read-back, handover, languages | Done, covered by tests |
| 2 | Voice: Gnani Prisma (STT) and Timbre (TTS), browser recorder | Done, tested on live calls |
| 3 | Control room: dashboard, dispatch, rescuer page, AI note-taker | Done |

195 backend tests, passing. Several replay real test calls word for word.

One live voice turn measured: **speech to text 0.4 s, agent 1.2 s (one LLM call), voice 0.5 s**.
Short answers that don't need the LLM take a few milliseconds in the agent.

---

## Setup (Windows)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

On macOS / Linux, activate with `source .venv/bin/activate`.

Create `backend/.env` (it is in `.gitignore`, never commit it):

```
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=your-groq-key
LLM_MODEL=openai/gpt-oss-20b
GNANI_API_KEY=your-gnani-key
STT_LANGUAGES=hi-IN,en-IN,ta-IN,te-IN
```

Optional:
- `STT_CONTEXT=none` turns off the English question sent to Prisma as context. Try it if
  Indian-language answers start coming back in English letters.
- `LLM_MAX_TOKENS=2048` raises the token limit if the log shows "empty content". That error
  means the model used all its tokens on reasoning.
- `SUPPORTED_REPLY_LANGS`, if you set it, must list every language the agent replies in.

```powershell
cd frontend
npm install
```

## Run

```powershell
# backend
cd backend
uvicorn app.main:app --reload --port 8000

# frontend (second terminal), then open http://localhost:5173/#/call and #/dashboard
cd frontend
npm run dev

# or serve the built frontend from the backend at http://localhost:8000
npm run build

# tests
python -m pytest -q

# a test call in the terminal (text mode, no Gnani credits used)
python scripts/chat_cli.py

# check the Gnani key, speed and language detection (uses a few credits)
python scripts/gnani_check.py
```

### Debugging a call

Every voice turn's response (browser DevTools → Network → `turn` → Response) includes:
- `lang_check`: what Prisma heard, what the LLM said the language was, and whether the call switched.
- `understood`: how the turn was read (question type, "don't know", panic, and whether the LLM failed).

The backend log prints `LLM HTTP …` or `extract failed …` when the LLM call fails.

---

## Project layout

```
backend/
  app/
    dialogue.py     the call engine: what to ask next, read-back, close, handover, off-script turns
    priority.py     fixed P0–P3 rules
    quick_parse.py  short answers (numbers, yes/no, PIN codes) understood without the LLM
    prompts.py      the LLM extraction prompt and the greeting
    phrases.py      reviewed lines in each language
    language.py     language detection, per-turn language judging, per-call language tracking
    gazetteer.py    localities → coordinates; street names into English letters; PIN codes
    llm.py          LLM client, output cleaning and retries
    notes.py        AI note-taker and notes check
    dispatch.py     rescue teams, assignment, shifts, SMS text
    models.py       ticket and extraction data models
    store.py        ticket storage (SQLite)
    config.py       settings
    main.py         API
    voice/
      stt.py        Gnani Prisma speech to text
      tts.py        Gnani Timbre text to speech
      call.py       one voice turn: audio in → reply audio out
      gnani_http.py shared HTTP client with retries
  scripts/          chat_cli, gnani_check, prewarm_voice, voice_cli
  tests/
frontend/
  src/
    pages/          Dashboard, CallScreen, Rescuer
    components/     Queue, MapView, DepthGauge, TicketDetail, LiveCall, OperatorCall, Notes
    lib/            recorder, useVoiceCall, useOperatorCall, scenarios, api
```

---

## Known limitations

- **The locality list is demo data for one test city** (about 30 localities, with approximate
  area-centre coordinates). A pin marks the area, not the house. Deploying elsewhere means
  loading that area's localities into `gazetteer.py`.
- **PIN codes aren't on the map yet.** They're saved and read back, but not turned into
  coordinates, and the dashboard's ticket detail doesn't show them yet.
- **Prisma sometimes mishears similar-sounding words** (నీళ్ళు "water" → వీళ్ళు "these people").
  The agent asks rather than guesses, but a headset and clear speech help a lot.
- **The Tamil lines need a check by a Tamil speaker.**
- **Callbacks and follow-ups are flagged on the ticket;** making the calls is not built yet.
- Ideas discussed, not built: shelters on the map, spotting a repeat call about the same case,
  and flagging claims that don't match nearby reports.