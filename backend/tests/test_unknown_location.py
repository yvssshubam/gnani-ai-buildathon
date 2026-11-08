"""From a live call: a caller who doesn't know where they are, and doesn't understand a question."""
from app import phrases
from app.dialogue import CallSession
from app.models import Extraction, Ticket


class _Store:
    def save(self, t):
        pass


class _LLM:
    def __init__(self, table):
        self.table = table

    def extract(self, text, last_question, known):
        return Extraction(**self.table.get(text, {}))


def session(table):
    return CallSession(Ticket(id="8001", caller_number="x"), _LLM(table), _Store())


def test_dont_know_where_i_am_leads_to_what_can_you_see_not_the_street():
    s = session({
        "चाला घोरंगा उंदी": dict(needs=["rescue"]),
        "किसी को भी चोट नहीं लगी है और पानी नी तक आ रहा है": dict(injured=False, water_level="knee"),
        "मैं पता नहीं मैं कहाँ पे हूँ": dict(dont_know=True),
        "कुछ दिख नहीं रहा, बहुत पानी है": dict(dont_know=True),
    })
    s.handle("चाला घोरंगा उंदी", "hi-IN")
    assert s.handle("किसी को भी चोट नहीं लगी है और पानी नी तक आ रहा है", "hi-IN")["action"] == "ask:area"
    r = s.handle("मैं पता नहीं मैं कहाँ पे हूँ", "hi-IN")
    assert r["action"] == "ask:area" and phrases.say("area2", "hi-IN") in r["reply"]
    r = s.handle("कुछ दिख नहीं रहा, बहुत पानी है", "hi-IN")
    assert phrases.say("area3", "hi-IN") in r["reply"]                 # what can you SEE near you
    assert phrases.say("street1", "hi-IN") not in r["reply"]           # not "which street, house number"


def test_after_the_landmark_question_it_moves_on_and_flags_a_callback():
    s = session({
        "help, water everywhere, nobody hurt": dict(injured=False, needs=["rescue"]),
        "I don't know where I am": dict(dont_know=True),
        "I don't know": dict(dont_know=True),
        "I can't see anything": dict(dont_know=True),
    })
    s.handle("help, water everywhere, nobody hurt", "en-IN")
    s.handle("I don't know where I am", "en-IN")
    s.handle("I don't know", "en-IN")
    r = s.handle("I can't see anything", "en-IN")
    assert r["action"] not in ("ask:area", "ask:street")               # no more location questions
    assert phrases.say("street1", "en-IN") not in r["reply"] and phrases.say("street2", "en-IN") not in r["reply"]


def test_a_landmark_given_with_dont_know_is_used_and_not_asked_again():
    s = session({
        "help, nobody hurt": dict(injured=False),
        "I don't know, near some temple": dict(dont_know=True, landmark="Some Temple"),
    })
    s.handle("help, nobody hurt", "en-IN")
    s.handle("I don't know, near some temple", "en-IN")     # area asked once more, in simpler words
    r = s.handle("I don't know, near some temple", "en-IN")
    assert r["action"] == "ask:floor"                         # landmark known: no street or "what can you see"


def test_what_does_floor_mean_is_asked_again_in_simpler_words_without_an_echo():
    s = session({
        "help, nobody hurt, we are in Velachery": dict(injured=False, locality="Velachery"),
        "అంతస్తు అంటే ఏంటి?": dict(caller_question="rephrase", spoken_language="te-IN",
                                    ack="అంతస్తు అంటే ఏంటి, అర్థమైంది"),
    })
    first = s.handle("help, nobody hurt, we are in Velachery", "en-IN")
    assert first["action"] == "ask:street"
    s.lang.current = "te-IN"           # the call is in Telugu by now
    r = s.handle("అంతస్తు అంటే ఏంటి?", "te-IN")
    assert "అర్థమైంది" not in r["reply"]                                # no "what is floor, understood"
    assert r["reply"].startswith(phrases.say("rephrase", "te-IN"))
    assert phrases.say("street2", "te-IN") in r["reply"]               # the simpler wording of the same question
    assert s.stuck_turns == 0


def test_every_language_has_the_rephrase_line():
    for lang in ("en-IN", "hi-IN", "ta-IN", "te-IN"):
        assert phrases.has("rephrase", lang)


# ---------------------------------------------------------------- "building? it's our house"

def test_our_house_is_not_a_building_name():
    from app.llm import clean_extraction, is_generic_place
    # the live call: "building అంటే మా ఇల్లుంది" became the building "Maa Illundhi"
    e = clean_extraction({"building": "Maa Illundhi", "building_native": "మా ఇల్లుంది"})
    assert e.building is None and e.building_native is None
    for generic in ("our house", "my home", "हमारा घर", "Hamara ghar", "எங்க வீடு", "Enga veedu", "ఇక్కడ"):
        assert is_generic_place(generic), generic
    for name in ("Lotus Apartments", "Sai Home", "Nehru Street", "Green House Apartments",
                 "Housing Board Colony", "Building 4", "Ganesh Temple", "నెహ్రూ స్ట్రీట్"):
        assert not is_generic_place(name), name
    # a native-only generic answer is dropped too
    assert clean_extraction({"landmark_native": "हमारा घर"}).landmark_native is None
    # real fields next to it are kept
    e = clean_extraction({"building": "Maa Illundhi", "locality": "Velachery", "floor": "first"})
    assert (e.building, e.locality, e.floor) == (None, "Velachery", "first")


def test_after_our_house_the_address_is_still_asked_for():
    s = session({
        "help, nobody hurt, we are in Velachery": dict(injured=False, locality="Velachery"),
    })
    first = s.handle("help, nobody hurt, we are in Velachery", "en-IN")
    assert first["action"] == "ask:street"
    from app.llm import clean_extraction
    s.llm = _LLM({})
    s.llm.extract = lambda *a: clean_extraction({"building": "Maa Illundhi", "building_native": "మా ఇల్లుంది"})
    r = s.handle("building అంటే మా ఇల్లుంది", "te-IN")
    assert s.ticket.location.building is None
    assert r["action"] == "ask:street"            # still asking where the house is


# ---------------------------------------------------------------- "shall I tell you?" and fear for life

def test_shall_i_tell_you_gets_yes_tell_me_and_the_answer_still_counts():
    s = session({
        "help, nobody hurt": dict(injured=False),
        "నేను మా ఇల్లు దగ్గర ఉన్నా, అది నాకు తెలుసు. చెప్పనా?": dict(caller_question="go_ahead",
                                                               ack="మా ఇల్లు, అర్థమైంది"),
        "వేళచ్చేరి, నెహ్రూ స్ట్రీట్": dict(locality="Velachery", street="Nehru Street"),
    })
    s.handle("help, nobody hurt", "en-IN")
    s.lang.current = "te-IN"
    r = s.handle("నేను మా ఇల్లు దగ్గర ఉన్నా, అది నాకు తెలుసు. చెప్పనా?", "te-IN")
    assert r["action"] == "go_ahead"
    assert r["reply"] == phrases.say("go_ahead", "te-IN")             # just "yes, tell me": no echo, no new question
    assert s.last_action.key == "ask:area" and s.stuck_turns == 0     # still waiting for the area
    r = s.handle("వేళచ్చేరి, నెహ్రూ స్ట్రీట్", "te-IN")
    assert s.ticket.location.locality == "Velachery" and s.ticket.location.street == "Nehru Street"


def test_shall_i_tell_you_cant_loop_forever():
    s = session({"help, nobody hurt": dict(injured=False), "बताऊँ?": dict(caller_question="go_ahead")})
    s.handle("help, nobody hurt", "hi-IN")
    actions = [s.handle("बताऊँ?", "hi-IN")["action"] for _ in range(3)]
    assert actions[:2] == ["go_ahead", "go_ahead"] and actions[2] != "go_ahead"


def test_fear_for_life_gets_the_calming_line_and_the_simple_question():
    s = session({"मैं मरने वाला": dict(panic="high")})
    r = s.handle("मैं मरने वाला", "hi-IN")
    assert phrases.say("calm", "hi-IN") in r["reply"]
    assert phrases.say("danger2", "hi-IN") in r["reply"]               # "Is anyone hurt? Yes or no."


def test_every_language_has_the_go_ahead_line():
    for lang in ("en-IN", "hi-IN", "ta-IN", "te-IN"):
        assert phrases.has("go_ahead", lang)


def test_shall_i_tell_you_is_caught_even_when_the_llm_misses_it():
    """The live call: "I don't know a school or bus stop, but I know the address. Shall I tell you?" """
    line = "school bus stop తెలియదు, కానీ నాకు నేను వెళ్ళే address తెలుసు. అక్కడే ఉన్నాను, చెప్పమంటావా?"
    s = session({
        "నీళ్ళు చాలా ఎక్కువ ఉన్నాయి": dict(water_rising=True, panic="high"),
        line: dict(dont_know=True, caller_question="other"),          # what the LLM gave back
    })
    s.handle("నీళ్ళు చాలా ఎక్కువ ఉన్నాయి", "te-IN")
    r = s.handle(line, "te-IN")
    assert r["action"] == "go_ahead" and r["reply"] == phrases.say("go_ahead", "te-IN")
    assert r["understood"]["caller_question"] == "go_ahead"


def test_offer_patterns():
    from app.dialogue import offers_to_tell
    for yes in ("చెప్పనా?", "చెప్పమంటావా?", "बताऊँ?", "क्या मैं बता दूँ", "shall I tell you?",
                "Should I explain?", "சொல்லட்டுமா?", "bataun kya?", "cheppamantava"):
        assert offers_to_tell(yes), yes
    for no in ("मैं नहीं बता सकता", "I can't tell", "నాకు తెలియదు", "we are in Velachery", "tell me fast"):
        assert not offers_to_tell(no), no


def test_an_offer_with_the_address_in_it_is_just_an_answer():
    line = "let me tell you, we are in Velachery"
    s = session({"help, nobody hurt": dict(injured=False), line: dict(locality="Velachery")})
    s.handle("help, nobody hurt", "en-IN")
    assert s.handle(line, "en-IN")["action"] != "go_ahead"