# Voice review: how to hear and fix the agent's delivery

Three problems were reported: the voice ignores the emotion of the line, it can sound seductive,
and the spacing between phrases is bad. What causes each, and where it is controlled:

| Problem | Cause | Control |
|---|---|---|
| Spacing | Each part of a reply was its own clip, played one after another in the browser. Every join added the clip's own silence plus a fetch: close to a second of dead air after "ठीक है।". Colons got no pause. | `TTS_GAP_MS` (default 280 ms, half after a one-word ack). Parts are joined on the server (`voice/stitch.py`). `TTS_STITCH=0` restores the old way for an A/B. |
| Flat, same tone for every line | Timbre v2.5 has no emotion setting. Every line was made once at speed 1.0. | `TTS_PACE` per kind of line (`voice/delivery.py`): urgent lines quicker, instructions and closing slower, read-back slowest. On Timbre v3.0, `TTS_TAGS` adds an audio tag per kind of line. |
| Seductive | A "soft", "gentle" voice, speaking intimate words ("मैं आपके साथ हूँ, एक लंबी साँस लीजिए"), slowly, in short isolated clips. | The target is calm and steady, not soft. Choose a composed voice with `scripts/voice_audition.py`. The calming line now gives the caller a task instead of intimacy. |

## Listening session (about 20 minutes)

1. `python scripts\voice_audition.py` makes the same six moments in each shortlisted voice, in
   `backend\voice_audition\<lang>\<model>_<voice>\`.
2. Listen **one moment across all voices** (all the `3_panicking_caller.wav` files, then all the
   `4_urgent.wav` files), not one voice through all moments. Differences show up that way.
3. For each voice, mark:
   - Does `4_urgent` sound more urgent than `2_ack_then_question`? If not, the voice is flat.
   - Does `3_panicking_caller` sound steady, or breathy and close? Breathy means drop the voice.
   - In `5_readback`, can you write the PIN code down as you hear it?
   - Is there any gap that makes you wonder if the line dropped?
4. Pick one voice. If it is a v3.0 voice, put it in `.env` for every language (see `.env.example`),
   then `python scripts\prewarm_voice.py` and test a full call on `#/call`.
5. Tune only if needed: `TTS_GAP_MS` (200 to 350), `TTS_PACE`, and on v3.0 `TTS_TAGS=readback:<slow>`.

## Timbre v3.0 audio tags

The 13 tags are `<laugh> <giggle> <sigh> <exhales> <sniffles> <yawns> <coughs> <clears throat>
<whispers> <shouting> <excited> <slow> <pauses>`. A tag applies from where it sits to the next tag
or the end of the text. There is no calm, serious or concerned tag. For an emergency line only
`<slow>` (read-backs) and `<pauses>` are useful. `<whispers>`, `<sigh>` and `<exhales>` push toward
exactly the intimate sound to avoid, and `<excited>` and `<giggle>` don't belong on this line.
Gnani doesn't say which languages the tags work in, so check Telugu and Tamil by ear.
