# Flood SOS Line, Chennai

A phone line that answers flood rescue calls when every human operator is busy. It talks to
the caller in their own language, collects what rescuers need (where they are, how many
people, who is vulnerable, how high the water is), reads it back for confirmation and turns
the call into a prioritised rescue ticket.

Built as a solo entry for Gnani AI's Great Indian AI Internship Challenge.
It is a **prototype tested on synthetic calls**, not a deployed service.

---

## The problem

During the 2015 Chennai floods and Cyclone Michaung (2023), helplines went unanswered under
the surge of calls, phone networks failed, and social media became the SOS channel by
default. Volunteer teams were handling up to 2,000 requests a day. Every request also has to
pass through a control room that coordinates many departments, and details can get lost
or changed at each handover. Chennai is also home to many people who don't speak Tamil.

This line is meant to **add capacity next to human operators**, not replace them: the AI
takes calls only when no person is free, and hands over to a human whenever the call needs one.

---

## How a call works

```
caller speaks ──► speech-to-text (Gnani Prisma) ──► language tracking
                                                    │
         short answer ("4", "haan", "முட்டி")  ◄────┤────► longer sentence
         understood by plain code, no LLM            │     one LLM call extracts the facts
                                                    ▼
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

- **What the caller hears is fixed and reviewed** (`app/phrases.py`). The LLM only adds a
  short acknowledgement of what the caller said, and code throws it away if it is too long,
  in the wrong language, or sounds like a promise ("the boat is coming in 10 minutes").
- **The call never loops.** If the caller gives nothing new for 3 turns in a row (2 if they
  are panicking), repeats the same question, or says "I don't know" to everything, the call
  is handed to a human officer with the ticket number.
- **Tickets are in English, with the caller's own words kept.** Street names given in Tamil,
  Hindi or Telugu script are converted to English letters for responders (`नेहरू स्ट्रीट` →
  `Nehru Street`), and the original stays for the read-back.
- **Tickets that need a human say so.** If the location is only known to area level, the call
  drops mid-way, or a stable P2 case has water, the ticket gets a follow-up reason
  (for example, re-check the water level in 30 minutes).

---

## Languages

| Caller speaks or types | Status |
|---|---|
| Tamil, Hindi, Telugu, English | Tested in text mode |
| Mixed with English ("हम Madipakkam में हैं", "Church Road, first floor") | Tested |
| Typed in English letters: Hinglish ("hum velachery mein hain"), Tanglish, Telugu | Tested |
| Other Indian languages in their own script | Detected; the reply falls back to Hindi and the ticket is flagged "interpreter needed" |
| Other Indian languages in English letters | Not supported yet (read as English) |

The call keeps one language and only switches after two turns in a row in a new language,
so one English phrase like "first floor" doesn't flip the conversation, but a phone handed to
a neighbour who speaks another language does.

---

## Status

| Phase | What | State |
|---|---|---|
| 1 | Call engine in text mode: extraction, triage, read-back, handover, languages | Done, covered by tests |
| 2 | Voice: Gnani Prisma (STT) and Timbre (TTS) | In progress |
| 3 | Control-room dashboard: map with priority pins | Planned |

Measured on text-mode test calls: about **3 LLM calls per call** (~2,600 tokens),
**0.5–0.8 s** for turns that use the LLM and **~5 ms** for short answers that don't.

---

## Setup (Windows)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

On macOS / Linux, activate with `source .venv/bin/activate`.

Create `backend/.env` (it is in `.gitignore`, never commit it):

```
GNANI_API_KEY=your-gnani-key
<!-- TODO: add the LLM key variable exactly as named in app/config.py -->
```

## Run

```bash
# a test call in the terminal (text mode, no Gnani credits used)
python scripts/chat_cli.py

# check the Gnani key, speed and language detection (uses a few credits)
python scripts/gnani_check.py

# tests
python -m pytest -q
```

---

## Project layout

```
backend/
  app/
    dialogue.py     the call engine: what to ask next, read-back, close, handover
    priority.py     fixed P0–P3 rules
    quick_parse.py  short answers understood without the LLM
    prompts.py      the LLM extraction prompt
    phrases.py      reviewed lines in each language
    language.py     language detection (script and words) and per-call language tracking
    gazetteer.py    Chennai localities → coordinates; street names into English letters
    llm.py          LLM client
    models.py       ticket and extraction data models
    store.py        ticket storage
    config.py       settings
  scripts/
    chat_cli.py     text-mode test call
    gnani_check.py  Gnani API check
  tests/
```

---

## Known limitations

- Locality coordinates are approximate area centres, so a pin marks the area, not the house.
- Only around 30 Chennai localities are in the gazetteer so far.
- The dialogue has been tested on synthetic, typed calls. Voice testing with recorded and
  noisy audio is the next step.
- Callbacks and follow-ups are flagged on the ticket; making the calls is not built yet.