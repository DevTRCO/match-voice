"""Voice delivery: energy, voice settings, text shaping, and the (unexercised) GuardedTTS delivery path with a fake synthesiser."""
import asyncio

import pytest

from matchvoice.commentary.delivery import (ENERGIES, VOICE_SETTINGS, energy_of, number_words, shape_for_tts, voice_settings)
from matchvoice.commentary.lang import LANGS, STYLES
from matchvoice.commentary.moments import Moment, render_variants
from matchvoice.tts import MODEL, GuardedTTS
from matchvoice.tts.fake import FakeSynth
from test_commentary import build


def moment(kind="x", priority=50, **params) -> Moment:
    return Moment(id=1, t=0.0, clock="10", kind=kind, voice="pbp", priority=priority, ttl=10, params=params)


# ---------- energy ----------
def test_energy_follows_priority_and_tags():
    assert energy_of(moment(priority=30)) == "calm"
    assert energy_of(moment(priority=60)) == "rising"
    assert energy_of(moment("shot_goal", 100)) == "peak"
    assert energy_of(moment("red", 95)) == "peak"
    assert energy_of(moment("goal_analysis", 70, tags="opener")) == "rising"
    assert energy_of(moment("goal_analysis", 70, tags="equaliser")) == "peak"
    assert energy_of(moment("goal_analysis", 70, tags="late,go_ahead")) == "peak"
    assert energy_of(moment("momentum", 55)) == "rising"
    assert energy_of(moment("big_save_analysis", 50, xg=0.56)) == "rising"
    assert energy_of(moment("big_save_analysis", 50, xg=0.1)) == "calm"


def test_a_whistle_is_never_peak():
    assert energy_of(moment("half_time", 85)) == "rising"
    assert energy_of(moment("full_time", 90)) == "rising"


# ---------- voice settings ----------
def test_voice_settings_table_is_monotone_and_inside_the_api_ranges():
    stab = [VOICE_SETTINGS[e]["stability"] for e in ENERGIES]
    speed = [VOICE_SETTINGS[e]["speed"] for e in ENERGIES]
    style = [VOICE_SETTINGS[e]["style"] for e in ENERGIES]
    assert stab == sorted(stab, reverse=True) and speed == sorted(speed) and style == sorted(style)
    for e in ENERGIES:
        s = VOICE_SETTINGS[e]
        assert 0 <= s["stability"] <= 1 and 0 <= s["similarity_boost"] <= 1 and 0 <= s["style"] <= 1 and 0.7 <= s["speed"] <= 1.2


def test_flash_gets_no_style_and_a_speaker_boost():
    s = voice_settings("peak", MODEL)
    assert "style" not in s and s["use_speaker_boost"] is True and s["speed"] == VOICE_SETTINGS["peak"]["speed"]


# ---------- text shaping ----------
@pytest.mark.parametrize("lang,text,expected", [
    ("en", "It's 1-1.", "It's one-all."),
    ("en", "Now 0-0 at the break.", "Now nil-nil at the break."),
    ("en", "It is 2-1 to Harbour.", "It is two-one to Harbour."),
    ("en", "A 0-1 lead.", "A nil-one lead."),
    ("de", "Es steht 1-1.", "Es steht eins zu eins."),
    ("de", "Jetzt 0-2 hinten.", "Jetzt null zu zwei hinten."),
    ("fr", "Et c'est 1-1 !", "Et c'est un partout!"),
    ("fr", "Le score reste 0-0.", "Le score reste zéro partout."),
    ("de", "1:1, noch knapp zwanzig Minuten.", "eins zu eins, noch knapp zwanzig Minuten."),  # German writes 1:1 and says "eins zu eins"
    ("fr", "Wexmoor mène 2-1 !", "Wexmoor mène deux à un!"),
])
def test_scorelines_become_spoken_forms(lang, text, expected):
    assert shape_for_tts(text, lang) == expected


def test_percent_decimals_and_abbreviations():
    assert shape_for_tts("A chance worth 0.25 xG.", "en") == "A chance worth zero point two five expected goals."
    assert shape_for_tts("Eine Chance mit 0,25 xG.", "de") == "Eine Chance mit null Komma zwei fünf erwartete Tore."
    assert shape_for_tts("Une occasion à 0,58 xG.", "fr") == "Une occasion à zéro virgule cinq huit buts attendus."
    assert shape_for_tts("Up to 36% to win.", "en") == "Up to thirty-six percent to win."
    assert shape_for_tts("Jetzt 84 Prozent.", "de") == "Jetzt vierundachtzig Prozent."
    assert shape_for_tts("Plus que 84 % de chances.", "fr") == "Plus que quatre-vingt-quatre pour cent de chances."
    assert shape_for_tts("Flat out at 31 km/h.", "en") == "Flat out at 31 kilometres per hour."


def test_ordinals():
    assert shape_for_tts("In the 71st minute.", "en") == "In the seventy-first minute."
    assert shape_for_tts("The 14th minute.", "en") == "The fourteenth minute."
    assert shape_for_tts("Das Tor in der 14. Minute.", "de") == "Das Tor in der vierzehnten Minute."
    assert shape_for_tts("Die 71. Minute läuft.", "de") == "Die einundsiebzigste Minute läuft."
    assert shape_for_tts("À la 71e minute.", "fr") == "À la soixante et onzième minute."
    assert shape_for_tts("À la 1re minute.", "fr") == "À la première minute."


def test_pauses_and_endings():
    assert shape_for_tts("Half time: Harbour lead - just.", "en") == "Half time. Harbour lead, just."
    assert shape_for_tts("Saved", "en") == "Saved."
    assert shape_for_tts("Tor!!!", "de") == "Tor!"
    assert shape_for_tts("Mi-temps : un à zéro", "fr") == "Mi-temps. un à zéro."
    assert "  " not in shape_for_tts("a    b ;  c", "en")


def test_number_words_cover_zero_to_ninety_nine():
    assert [number_words(n, "en") for n in (0, 13, 21, 40, 99)] == ["zero", "thirteen", "twenty-one", "forty", "ninety-nine"]
    assert [number_words(n, "de") for n in (0, 16, 21, 30, 99)] == ["null", "sechzehn", "einundzwanzig", "dreißig", "neunundneunzig"]
    assert [number_words(n, "fr") for n in (0, 17, 21, 71, 80, 81, 91, 99)] == [
        "zéro", "dix-sept", "vingt et un", "soixante et onze", "quatre-vingts", "quatre-vingt-un", "quatre-vingt-onze", "quatre-vingt-dix-neuf"]
    assert number_words(120, "en") == "120"


def test_shaped_template_lines_have_no_digits_left_that_matter_and_no_abbreviations():
    meta, _, _, _, moments, _ = build("comeback")
    for m in moments:
        for lang in LANGS:
            for style in STYLES:
                for text in render_variants(m, lang, style):
                    shaped = shape_for_tts(text, lang)
                    assert "%" not in shaped and "xG" not in shaped and "km/h" not in shaped and "–" not in shaped and " - " not in shaped, shaped
                    assert not any(f"{a}-{b}" in shaped for a in range(10) for b in range(10)), shaped
                    assert shaped[-1] in ".!?" and shape_for_tts(shaped, lang) == shaped, shaped  # idempotent


# ---------- GuardedTTS delivery path, fake synthesiser only ----------
def test_delivery_is_off_by_default_so_text_and_cache_are_unchanged(tmp_path):
    fake = FakeSynth()
    t = GuardedTTS(fake, 300, MODEL, tmp_path / "tts")
    asyncio.run(t.speak("It's 1-1.", "en", "peak"))
    assert fake.calls[0][0] == "It's 1-1." and fake.settings == [None] and t.spent == 5


def test_delivery_on_sends_shaped_text_and_energy_settings_and_bills_what_is_sent(tmp_path):
    fake = FakeSynth()
    t = GuardedTTS(fake, 300, MODEL, tmp_path / "tts", delivery=True)
    audio, hit = asyncio.run(t.speak("It's 1-1.", "en", "peak"))
    assert not hit and fake.calls[0][0] == "It's one-all." and fake.settings[0]["stability"] == VOICE_SETTINGS["peak"]["stability"]
    assert t.spent == 7  # 13 characters sent, 0.5 per character, rounded up
    asyncio.run(t.speak("It's 1-1.", "en", "peak"))
    assert len(fake.calls) == 1  # cached
    asyncio.run(t.speak("It's 1-1.", "en", "calm"))
    assert len(fake.calls) == 2 and fake.settings[1]["stability"] == VOICE_SETTINGS["calm"]["stability"]  # another energy is another take
    asyncio.run(t.speak("It's 1-1.", "en"))
    assert fake.settings[2] is None  # no energy, no settings


def test_hype_stretches_the_goal_call_and_tags_only_for_a_tag_model():
    from matchvoice.commentary.delivery import hype_for_tts
    assert hype_for_tts("GOAL! Fontaine buries it, and it's one-all!", "en", "peak", "eleven_v3") == "[shouting] GOOOAL! Fontaine buries it, and it's one-all!"
    assert hype_for_tts("TOR! Fontaine macht ihn rein.", "de", "peak", "eleven_flash_v2_5") == "TOOOR! Fontaine macht ihn rein!"
    assert hype_for_tts("BUT ! Fontaine ne tremble pas.", "fr", "peak", "eleven_flash_v2_5").startswith("BUUUT! Fontaine")
    assert hype_for_tts("Goalkeeper Rourke is up.", "en", "peak", "eleven_flash_v2_5") == "Goalkeeper Rourke is up!"  # not a shout word
    assert hype_for_tts("Calm line.", "en", "calm", "eleven_v3") == "Calm line."
