"""Areas not on our map list get a pin from OpenStreetMap's address search (no internet in tests)."""
import pytest

from app import dialogue, geocode
from app.dialogue import OFF_MAP_REASON, CallSession
from app.models import Extraction, Location, Ticket


class _Resp:
    def __init__(self, hits):
        self.hits = hits

    def raise_for_status(self):
        pass

    def json(self):
        return self.hits


class FakeHTTP:
    """Answers like Nominatim: Sainikpuri and PIN 500094 are in Hyderabad."""
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params)
        assert headers["User-Agent"] and params["countrycodes"] == "in" and params["format"] == "jsonv2"
        if self.fail:
            raise OSError("no internet")
        text = (params.get("q") or params.get("postalcode") or "").lower()
        if "sainikpuri" in text or "500094" in text:
            return _Resp([{"lat": "17.4930", "lon": "78.5530", "display_name": "Sainikpuri, Hyderabad"}])
        return _Resp([])


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    geocode._cache.clear()
    monkeypatch.setattr(geocode, "_last_request", 0.0)
    monkeypatch.setattr(geocode.time, "sleep", lambda s: None)


class _Store:
    saved = 0

    def save(self, t):
        self.saved += 1


def test_area_with_pin_code_is_placed_and_flag_updated():
    t = Ticket(id="1", caller_number="x", location=Location(locality="Sainikpuri", pincode="500094"))
    t.followup_reasons.append(OFF_MAP_REASON)
    http, store = FakeHTTP(), _Store()
    assert geocode.place(t, store, OFF_MAP_REASON, http)
    assert (t.location.lat, t.location.lon) == (17.493, 78.553)
    assert OFF_MAP_REASON not in t.followup_reasons and geocode.FOUND_REASON in t.followup_reasons
    assert store.saved == 1
    assert http.calls[0]["q"] == "Sainikpuri, 500094, India"


def test_pin_code_alone_is_looked_up_as_a_postal_code():
    t = Ticket(id="2", caller_number="x", location=Location(pincode="500094"))
    http = FakeHTTP()
    assert geocode.place(t, _Store(), OFF_MAP_REASON, http)
    assert http.calls == [{"postalcode": "500094", "country": "India", "format": "jsonv2", "limit": 1, "countrycodes": "in"}]


def test_each_area_is_asked_for_once():
    http = FakeHTTP()
    for _ in range(3):
        geocode.lookup(Location(locality="Sainikpuri"), http)
    assert len(http.calls) == 1


def test_not_found_or_no_internet_leaves_the_ticket_as_it_was():
    t = Ticket(id="3", caller_number="x", location=Location(locality="Nowhereville"))
    assert not geocode.place(t, _Store(), OFF_MAP_REASON, FakeHTTP())
    t2 = Ticket(id="4", caller_number="x", location=Location(locality="Sainikpuri"))
    assert not geocode.place(t2, _Store(), OFF_MAP_REASON, FakeHTTP(fail=True))
    assert t.location.lat is None and t2.location.lat is None
    assert geocode.place(t2, _Store(), OFF_MAP_REASON, FakeHTTP())   # a failure isn't cached


class _LLM:
    def __init__(self, table):
        self.table = table

    def extract(self, text, last_question, known):
        return Extraction(**self.table[text])


def test_a_call_gets_a_pin_for_an_off_map_area(monkeypatch):
    monkeypatch.setattr(dialogue.settings, "geocode_enabled", True)
    http = FakeHTTP()
    monkeypatch.setattr(geocode, "place_in_background", lambda t, store, reason: geocode.place(t, store, reason, http))
    table = {"Sainikpuri, pin code 500094": dict(locality="Sainikpuri", pincode="500094", spoken_language="en-IN"),
             "sorry, it's Velachery": dict(locality="Velachery", spoken_language="en-IN"),
             "no wait, Kompally": dict(locality="Kompally", spoken_language="en-IN")}
    s = CallSession(Ticket(id="5", caller_number="x"), _LLM(table), _Store())
    s.greeting()
    s.handle("Sainikpuri, pin code 500094", "en-IN")
    assert s.ticket.location.lat == 17.493 and OFF_MAP_REASON not in s.ticket.followup_reasons
    s.handle("sorry, it's Velachery", "en-IN")             # on our own list: its own pin
    assert s.ticket.location.lat == pytest.approx(12.98, abs=0.01)
    s.handle("no wait, Kompally", "en-IN")                 # a new area: looked up again, with the PIN code
    assert http.calls[-1]["q"] == "Kompally, 500094, India"


def test_changing_to_an_area_that_cant_be_found_leaves_no_stale_pin(monkeypatch):
    monkeypatch.setattr(dialogue.settings, "geocode_enabled", True)
    http = FakeHTTP()
    monkeypatch.setattr(geocode, "place_in_background", lambda t, store, reason: geocode.place(t, store, reason, http))
    table = {"Sainikpuri": dict(locality="Sainikpuri", spoken_language="en-IN"),
             "actually it is Nowhereville": dict(locality="Nowhereville", correction=True, spoken_language="en-IN")}
    s = CallSession(Ticket(id="6", caller_number="x"), _LLM(table), _Store())
    s.greeting()
    s.handle("Sainikpuri", "en-IN")
    assert s.ticket.location.lat == 17.493
    s.handle("actually it is Nowhereville", "en-IN")
    assert s.ticket.location.lat is None and OFF_MAP_REASON in s.ticket.followup_reasons
    assert geocode.FOUND_REASON not in s.ticket.followup_reasons


# ---------------------------------------------------------------- voice calls: the pin is on the same turn

def test_voice_turn_places_the_area_while_the_reply_is_spoken(monkeypatch, tmp_path):
    import asyncio
    from app.voice.call import VoiceState, voice_turn
    from app.voice.stt import Transcript

    monkeypatch.setattr(dialogue.settings, "geocode_enabled", True)
    http = FakeHTTP()
    real_place = geocode.place
    monkeypatch.setattr(geocode, "place", lambda t, store, reason: real_place(t, store, reason, http))

    class STT:
        async def transcribe(self, audio, **kw):
            return Transcript(text="Sainikpuri, pin code 500094", language="en-IN", seconds=0.1)

    class TTS:
        model = "timbre-v2.5"

        async def synthesize(self, text, lang, speed=None):
            await asyncio.sleep(0.05)
            return b""

        def cached_path(self, text, lang, speed=None):
            return tmp_path / "x.wav"

        def join(self, paths, gaps_ms):
            return tmp_path / "x.wav"

    table = {"Sainikpuri, pin code 500094": dict(locality="Sainikpuri", pincode="500094", spoken_language="en-IN")}
    s = CallSession(Ticket(id="7", caller_number="x"), _LLM(table), _Store())
    s.greeting()
    result = asyncio.run(voice_turn(s, VoiceState(reply_lang="hi-IN"), b"RIFF", "turn.wav", STT(), TTS()))
    assert result["ticket"]["location"]["lat"] == 17.493      # on this turn's ticket, not the next
    assert OFF_MAP_REASON not in result["ticket"]["followup_reasons"]