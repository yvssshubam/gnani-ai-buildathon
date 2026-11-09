"""Simulated callers for scripts/stress_test.py.

Each scenario is a person with a situation (facts), a way of behaving on the phone (behaviour),
the language they speak from which turn (langs), and what the ticket should end up saying (truth).
An LLM plays the caller from this; Surgeline answers; the result is scored against `truth`.

langs: [(from_turn, code)], code = "hi-IN" | "te-IN" | "ta-IN" | "en-IN", or "hi-IN-latn" for
Hindi typed/spoken in English letters (Hinglish). Turn 1 is the caller's first line.

truth keys (all optional): locality (part of the area name, any case), pincode, people_count,
vulnerable (each must be on the ticket), water_level, injured, priority, end ("waiting" = stays in
line for an officer, "done" = call ends, "handoff" = passed to an officer).
"""

SCENARIOS = [
    {
        "id": "hindi_family_calm",
        "title": "Hindi, calm, everything known",
        "facts": "You are in Velachery, Gandhi Street, house number 12, on the first floor. 4 people: you, your wife, "
                 "your mother who is 75, and your son who is 8. Water is at knee level and slowly rising. Nobody is hurt.",
        "behaviour": "Answer each question plainly. Confirm the read-back if it is right.",
        "langs": [(1, "hi-IN")],
        "truth": {"locality": "velachery", "people_count": 4, "vulnerable": ["elderly", "child"], "floor": "first",
                  "water_level": "knee", "injured": False, "priority": "P0", "end": "waiting"},
    },
    {
        "id": "telugu_panic_chest",
        "title": "Telugu, panicking, chest-deep water",
        "facts": "You are in Saidapet, near the big Shiva temple, on the ground floor, standing on a table. "
                 "3 people: you, your husband, your 2-year-old daughter. Water is at chest level and rising fast. Nobody is hurt yet.",
        "behaviour": "You are terrified. Start with 'I'm going to die, please save us'. Keep sentences short and broken. "
                     "Repeat 'please come fast' once or twice.",
        "langs": [(1, "te-IN")],
        "truth": {"locality": "saidapet", "people_count": 3, "vulnerable": ["infant"], "water_level": "chest",
                  "priority": "P0", "end": "waiting"},
    },
    {
        "id": "hindi_then_telugu_neighbour",
        "title": "Hindi, then the phone is handed to a Telugu neighbour",
        "facts": "You are in Adyar, Lake View Road, building Sai Residency, second floor. 5 people, including a "
                 "pregnant woman. Water is at waist level. Nobody is hurt.",
        "behaviour": "For your first two answers you are a Hindi speaker. From your third answer on, you are the "
                     "neighbour who took the phone: you speak only Telugu and answer the rest of the questions.",
        "langs": [(1, "hi-IN"), (3, "te-IN")],
        "truth": {"locality": "adyar", "people_count": 5, "vulnerable": ["pregnant"], "water_level": "waist",
                  "priority": "P1", "end": "waiting"},
    },
    {
        "id": "english_pin_code_only",
        "title": "English, only knows the PIN code",
        "facts": "You just moved here and don't know the area or street names. You know your PIN code: 600042. "
                 "You are 2 people, on the third floor. Water is at ankle level. Nobody is hurt, nobody old or young.",
        "behaviour": "When asked where you are, say you don't know the area but you know the PIN code, and ask "
                     "'is that okay?'. Say the PIN code digit by digit when asked for it.",
        "langs": [(1, "en-IN")],
        "truth": {"pincode": "600042", "people_count": 2, "water_level": "ankle", "injured": False,
                  "priority": "P2", "end": "done"},
    },
    {
        "id": "hindi_off_map_address",
        "title": "Hindi caller gives a full address off our map, in English",
        "facts": "You live in Sainikpuri, Sainath Colony, apartment 502, flat 501, fourth floor. 3 people. "
                 "Water is at knee level and rising. Two people have small cuts.",
        "behaviour": "When asked where you are, first say you don't know the area name, just that you're near your house. "
                     "Then ask 'should I tell you my house address?' and then say the full address in English words.",
        "langs": [(1, "hi-IN")],
        "truth": {"locality": "sainath colony", "people_count": 3, "water_level": "knee", "injured": True,
                  "priority": "P0", "end": "waiting"},
    },
    {
        "id": "hindi_wants_a_person",
        "title": "Hindi, insists on talking to a person",
        "facts": "You are in Tambaram, Station Road, first floor. 2 people, both adults. Water is at waist level.",
        "behaviour": "Your first words: you want to talk to a real person, not a machine. Answer one question if asked, "
                     "then ask for a person again. After that, only say short things like 'ok' or 'when will someone talk to me?'.",
        "langs": [(1, "hi-IN")],
        "truth": {"end": "waiting"},
    },
    {
        "id": "english_refuses_machine",
        "title": "English, refuses to talk to a machine",
        "facts": "You are in Porur. Water is at knee level. 4 people.",
        "behaviour": "Your first words: 'I won't talk to a machine, give me an officer'. After that, say 'ok' or give "
                     "one fact at a time if you feel like it.",
        "langs": [(1, "en-IN")],
        "truth": {"end": "waiting"},
    },
    {
        "id": "telugu_relative_status",
        "title": "Telugu, a relative asking when the boat will come",
        "facts": "You are calling for your parents, who are in Mylapore, Kutchery Road, house 7, ground floor. "
                 "2 people, both over 70. Water is at waist level. You are not there yourself.",
        "behaviour": "Start by asking when the boat will come for your parents. Answer the questions about them. "
                     "Ask again once, later, when help will come.",
        "langs": [(1, "te-IN")],
        "truth": {"locality": "mylapore", "people_count": 2, "vulnerable": ["elderly"], "water_level": "waist",
                  "priority": "P1", "end": "waiting"},
    },
    {
        "id": "hindi_angry",
        "title": "Hindi, angry and shouting",
        "facts": "You are in Anna Nagar, 3rd Avenue, house 45, on the terrace. 3 people including your 6-year-old. "
                 "Water is at waist level. Nobody is hurt.",
        "behaviour": "You are furious that nobody answered for an hour. Start with 'are you deaf? useless people!'. "
                     "Stay rude, but answer the questions.",
        "langs": [(1, "hi-IN")],
        "truth": {"locality": "anna nagar", "people_count": 3, "vulnerable": ["child"], "water_level": "waist",
                  "priority": "P1", "end": "waiting"},
    },
    {
        "id": "telugu_doesnt_understand",
        "title": "Telugu, doesn't understand some questions",
        "facts": "You are in Chromepet, near the bus stand, first floor. 4 people, one is sick with fever. "
                 "Water is at knee level. Nobody is hurt.",
        "behaviour": "You don't understand the word for 'floor' or 'vulnerable' when you hear it: ask what it means "
                     "('అంటే ఏంటి?'). Give very short answers.",
        "langs": [(1, "te-IN")],
        "truth": {"locality": "chromepet", "people_count": 4, "vulnerable": ["sick"], "water_level": "knee",
                  "priority": "P1", "end": "waiting"},
    },
    {
        "id": "hinglish_codemix",
        "title": "Hinglish in English letters",
        "facts": "You are in Madipakkam, Ram Nagar, flat 3B, second floor. 2 people. Water is at knee level. Nobody is hurt, "
                 "nobody old or young.",
        "behaviour": "Speak Hindi mixed with English, written in English letters: 'hum second floor pe hain, paani knee tak hai'.",
        "langs": [(1, "hi-IN-latn")],
        "truth": {"locality": "madipakkam", "people_count": 2, "water_level": "knee", "injured": False,
                  "priority": "P2", "end": "done"},
    },
    {
        "id": "tamil_corrects_readback",
        "title": "Tamil, corrects the read-back",
        "facts": "You are in Velachery, Taramani Road, house 9, second floor. 3 people. Water is at knee level. "
                 "Nobody is hurt, nobody old or young.",
        "behaviour": "At first say you are on the first floor. When the details are read back to you, correct it: "
                     "you are on the SECOND floor. Then confirm.",
        "langs": [(1, "ta-IN")],
        "truth": {"locality": "velachery", "people_count": 3, "floor": "second", "water_level": "knee",
                  "injured": False, "priority": "P2", "end": "done"},
    },
]