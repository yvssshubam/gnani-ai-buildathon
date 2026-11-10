"""How replies sound: one clip per reply with even gaps, pace per kind of line, digits as words."""
import asyncio
from array import array

import pytest

from app import phrases
from app.voice import delivery, stitch
from app.voice.call import speak
from app.voice.gnani_http import GnaniError
from app.voice.tts import TimbreTTS

RATE = 16000


def clip(quiet_before_ms, sound_ms, quiet_after_ms):
    n = lambda ms: RATE * ms // 1000
    samples = array("h", [0] * n(quiet_before_ms) + [4000, -4000] * (n(sound_ms) // 2) + [0] * n(quiet_after_ms))
    return stitch.write_wav(stitch.Clip(RATE, samples))


def test_trim_keeps_only_a_short_pad_around_the_sound():
    out = stitch.trim(stitch.read_wav(clip(400, 500, 600)))
    ms = len(out.samples) * 1000 // RATE
    assert 500 <= ms <= 500 + stitch.LEAD_PAD_MS + stitch.TAIL_PAD_MS + 10


def test_join_puts_exactly_our_gap_between_parts():
    joined = stitch.join([clip(300, 200, 500), clip(300, 200, 500)], [250, 0])
    ms = stitch.duration_ms(joined)
    pads = stitch.LEAD_PAD_MS + stitch.TAIL_PAD_MS
    # two sounds + their pads + one 250 ms gap; none of the clips' own 800 ms of silence each
    assert abs(ms - (200 + pads + 250 + 200 + pads)) <= 20


def test_join_refuses_audio_it_cant_read():
    with pytest.raises(stitch.CantStitch):
        stitch.join([b"RIFF" + b"\0" * 60], [0])


def test_all_quiet_clip_is_left_alone():
    c = stitch.read_wav(clip(300, 0, 300))
    assert len(stitch.trim(c).samples) == len(c.samples)


@pytest.mark.parametrize("lang,words", [
    ("hi-IN", "चार सात, दो एक"), ("en-IN", "four seven, two one"),
    ("te-IN", "నాలుగు ఏడు, రెండు ఒకటి"), ("ta-IN", "நாலு ஏழு, ரெண்டு ஒண்ணு"),
])
def test_ticket_number_is_said_as_words_in_two_pairs(lang, words):
    line = phrases.say("handoff", lang, digits="4 7 2 1")
    [piece] = delivery.pieces(line, lang)
    assert words in piece.text and "4 7" not in piece.text


def test_pin_code_is_said_as_two_groups_of_three():
    assert delivery.digits_as_words("pin code 5 0 0 0 9 4.", "en-IN") == "pin code five zero zero, zero nine four."
    assert delivery.digits_as_words("4 people, 2.5 feet", "en-IN") == "4 people, 2.5 feet"


def test_readback_is_split_and_the_details_are_slower():
    line = phrases.say("readback", "hi-IN", details="4 लोग, Sainikpuri, पिन कोड 5 0 0 0 9 4")
    intro, details, question = delivery.pieces(line, "hi-IN", "timbre-v2.5")
    assert intro.fixed and question.fixed and not details.fixed
    assert details.speed < intro.speed and "पाँच ज़ीरो ज़ीरो" in details.text
    assert question.text.endswith("?") and ":" not in intro.text
    assert details.gap_ms > intro.gap_ms   # a beat after the details, before "is that correct?"


def test_pace_follows_the_kind_of_line():
    say = lambda key: delivery.pieces(phrases.say(key, "hi-IN"), "hi-IN")[0]
    assert say("urgent").speed > say("danger1").speed > say("calm").speed
    assert say("ack").gap_ms < say("danger1").gap_ms   # no long pause after a one-word "okay"
    for key in ("urgent", "calm", "danger1"):
        assert 0.85 <= say(key).speed <= 1.15


def test_tags_only_reach_timbre_v3(monkeypatch):
    monkeypatch.setattr(delivery.settings, "tts_tags", "readback:<slow>")
    line = phrases.say("readback", "en-IN", details="4 people")
    assert not any("<" in p.text for p in delivery.pieces(line, "en-IN", "timbre-v2.5"))
    details = delivery.pieces(line, "en-IN", "timbre-v3.0")[1]
    assert details.text.startswith("<slow> ")


def test_prewarm_covers_the_fixed_halves_of_the_readback():
    texts = [t for t, _, _ in delivery.fixed_pieces(["hi-IN", "en-IN"])]
    assert "Let me check." in texts and "Is that correct?" in texts
    assert phrases.say("calm", "hi-IN") in texts and not any("{" in t for t in texts)


class FakeTTS(TimbreTTS):
    def __init__(self, tmp_path, fail_on=None):
        super().__init__(client=None, api_key="k", voices={"hi-IN": "Yashvi"}, fallback_lang="hi-IN",
                         model="timbre-v2.5", cache_dir=str(tmp_path / "cache"))
        self.fail_on, self.asked = fail_on, []

    async def synthesize(self, text, lang, speed=None):
        self.asked.append((text, speed))
        if self.fail_on and self.fail_on in text:
            raise GnaniError("TTS", 402, "", "no credit")
        self.cached_path(text, lang, speed).write_bytes(clip(300, 300, 400))
        return b""


def test_a_reply_plays_as_one_clip(tmp_path):
    tts = FakeTTS(tmp_path)
    parts = [phrases.say("ack", "hi-IN"), phrases.say("area1", "hi-IN")]
    urls, _, error = asyncio.run(speak(tts, parts, "hi-IN"))
    assert error is None and len(urls) == 1
    again, _, _ = asyncio.run(speak(tts, parts, "hi-IN"))
    assert again == urls   # the joined clip is cached too


def test_a_failed_part_falls_back_to_separate_clips(tmp_path):
    tts = FakeTTS(tmp_path, fail_on="आप कहाँ")
    parts = [phrases.say("ack", "hi-IN"), phrases.say("area1", "hi-IN")]
    urls, _, error = asyncio.run(speak(tts, parts, "hi-IN"))
    assert urls[0] and urls[1] is None and "402" in error
