"""The six world channels (es, it, pt, nl, tr, ja): channel ids and booths, the verifier's rules per language, Japanese names, the world
booth's prompt, and the runner end to end with a fake model and a private answer cache (no real call, nothing written to data/cache)."""
from __future__ import annotations

import asyncio
import json
import re

import pytest

from matchvoice.commentary.analyst import CallBudget
from matchvoice.commentary.delivery import score_said, shape_for_tts
from matchvoice.commentary.lang import ALL_KEYS, BOOTH, CORE_KEYS, WORLD_KEYS, who_of
from matchvoice.commentary.moments import Moment
from matchvoice.commentary.newsroom import finish_line
from matchvoice.commentary.verifier import JA_LOANWORDS, Verifier, allowed_for, kana_skeleton, skeleton
from matchvoice.commentary.world import WORLD_PROMPT_VERSION, WORLD_SYSTEM, about, build_world_prompt, room, world_moment
from matchvoice.pipeline import protocol as proto
from matchvoice.pipeline.library import Library
from matchvoice.pipeline.runner import LiveConfig, Runner

LIB = Library()
MATCH = "comeback-135"


@pytest.fixture(scope="module")
def bundle():
    return LIB.bundle(MATCH)


@pytest.fixture(scope="module")
def ver(bundle):
    return Verifier(bundle.meta)


SNAP = {"score": [1, 1], "stats": {s: {"possession": 0.5, "shots": 5, "on_target": 2, "xg": 0.7, "pass_acc": 0.8} for s in ("H", "A")},
        "win": [0.4, 0.3, 0.3]}


def moment(kind="pass_kind", voice="pbp", **params) -> Moment:
    return Moment(id=1, t=4384.4, clock="71", kind=kind, voice=voice, priority=27, ttl=3.0, params=params)


# ---------- channels and booths ----------
def test_world_channels_append_after_the_core_ones():
    assert ALL_KEYS[:6] == CORE_KEYS == ("en/beginner", "en/expert", "de/beginner", "de/expert", "fr/beginner", "fr/expert")
    assert WORLD_KEYS == ("es/expert", "it/beginner", "pt/expert", "nl/beginner", "tr/expert", "ja/beginner")
    assert [c["id"] for c in proto.ALL_CHANNELS] == list(range(12)) and [c["key"] for c in proto.ALL_CHANNELS] == list(ALL_KEYS)
    assert proto.CHANNELS == proto.ALL_CHANNELS[:6]


def test_booths_carry_name_gender_lang_and_level():
    want = {"es/expert": ("Lucía Romero", "woman"), "it/beginner": ("Giulia Conti", "woman"), "pt/expert": ("Rafael Souza", "man"),
            "nl/beginner": ("Sanne de Vries", "woman"), "tr/expert": ("Emre Aydın", "man"), "ja/beginner": ("Yuki Tanaka", "woman")}
    for key, (name, gender) in want.items():
        b = BOOTH[key]
        assert (b.lead.name, b.lead.gender, b.lang, b.level, b.solo) == (name, gender, key.split("/")[0], key.split("/")[1], True)
        ch = proto.ALL_CHANNELS[ALL_KEYS.index(key)]
        assert ch["lead"] == {"name": name, "gender": gender} and ch["solo"] is True and "co" not in ch and ch["level"] == ch["style"]
        assert who_of(key, "analyst") == who_of(key, "pbp") == name  # a solo booth: the lead says the analysis too
    assert proto.ALL_CHANNELS[2]["co"] == {"name": "Kim Berger", "gender": "woman"} and proto.ALL_CHANNELS[2]["solo"] is False
    assert all(c["lead"]["gender"] in ("man", "woman") for c in proto.ALL_CHANNELS)


def test_no_middle_dot_or_em_dash_in_the_booth_names_or_the_world_prompt():
    text = WORLD_SYSTEM + json.dumps(proto.ALL_CHANNELS, ensure_ascii=False)
    assert "—" not in text and "·" not in text.replace('"·"', "")  # the prompt names the forbidden dot once, in quotes


# ---------- the verifier, per language ----------
GOOD = {
    "es": "Ibsen la recupera y esta vez se va al otro lado, para Rasmussen.",
    "it": "Ibsen recupera la palla e questa volta va dall'altra parte.",
    "pt": "Ibsen rouba a bola e dessa vez a bola vai para o outro lado.",
    "nl": "Ibsen wint de bal en nu gaat hij wel naar de andere kant.",
    "tr": "Ibsen topu kaptı ve bu kez top hemen diğer kanada gitti.",
    "ja": "イブセンが奪って、今度はすぐ反対側のラスムッセンへ！",
}


def test_a_good_line_passes_in_every_world_language(bundle, ver):
    allowed = allowed_for(moment(player="Ibsen", target="Rasmussen"), SNAP, bundle.meta)
    for lang, text in GOOD.items():
        assert ver.check(text, lang, allowed, spelled=True).ok, (lang, ver.check(text, lang, allowed, spelled=True).feedback())


def test_the_wrong_language_is_caught(bundle, ver):
    allowed = allowed_for(moment(player="Ibsen", target="Rasmussen"), SNAP, bundle.meta)
    english = "Ibsen wins it, and this time it goes across to the other side."
    for lang in ("es", "it", "pt", "nl", "tr", "ja"):
        v = ver.check(english, lang, allowed)
        assert any(x.code == "language_mismatch" for x in v.violations), lang
    assert any(x.code == "language_mismatch" for x in ver.check(GOOD["ja"], "es", allowed).violations)  # kana on a Spanish channel
    assert any(x.code == "language_mismatch" for x in ver.check(GOOD["tr"], "nl", allowed).violations)
    assert ver.detect_lang(GOOD["es"], tuple(GOOD)) == "es" and ver.detect_lang(GOOD["nl"], tuple(GOOD)) == "nl"
    # the core channels are still checked among en, de and fr only, as before
    assert ver.detect_lang("Ibsen holt den Ball und spielt ihn auf die andere Seite.") == "de"


def test_numbers_scores_and_counts_per_language(bundle, ver):
    allowed = allowed_for(moment(player="Ibsen", target="Rasmussen"), SNAP, bundle.meta)
    assert any(x.code == "number_unsupported" for x in ver.check("Ibsen la ha recuperado siete veces.", "es", allowed, spelled=True).violations)
    assert any(x.code == "number_unsupported" for x in ver.check("イブセンが七回目のカット。", "ja", allowed, spelled=True).violations)
    assert ver.check("イブセン、十分な時間がある。", "ja", allowed, spelled=True).ok  # 十分な is "enough", not ten minutes
    assert ver.check("1対1、同点です！", "ja", allowed).ok
    assert any(x.code == "score_mismatch" for x in ver.check("2対1になりました。", "ja", allowed).violations)
    assert any(x.code == "score_mismatch" for x in ver.check("Ahora 2-1 para Wexmoor.", "es", allowed).violations)
    assert any(x.code == "count_in_beginner" for x in ver.check("Ibsen e tre passaggi, ed è gol.", "it", allowed, style="beginner").violations)
    assert any(x.code == "count_in_beginner" for x in ver.check("イブセンから3本のパスでゴール。", "ja", allowed, style="beginner").violations)
    assert any(x.code == "count_in_beginner" for x in ver.check("Ibsen en drie passes, en het is raak.", "nl", allowed, style="beginner").violations)


def test_claims_and_traits_per_language(bundle, ver):
    plain = allowed_for(moment(player="Ibsen", target="Rasmussen", pass_type="long"), SNAP, bundle.meta)
    switch = allowed_for(moment(player="Ibsen", target="Rasmussen", pass_type="switch"), SNAP, bundle.meta)
    for lang, text in (("es", "Cambio de orientación para Rasmussen."), ("it", "Cambio di gioco per Rasmussen."), ("pt", "Inversão para Rasmussen."),
                       ("tr", "Rasmussen'e çapraz pas."), ("ja", "ラスムッセンへサイドチェンジ！"), ("nl", "Een switch naar Rasmussen.")):
        assert any(x.code == "claim_unsupported" for x in ver.check(text, lang, plain).violations), lang
        assert ver.check(text, lang, switch).ok, (lang, ver.check(text, lang, switch).feedback())
    fontaine = allowed_for(moment(kind="shot_goal", player="Fontaine"), SNAP, bundle.meta)
    assert any(x.code == "trait_unsupported" for x in ver.check("¡Fontaine desde lejos!", "es", fontaine).violations)
    assert any(x.code == "trait_unsupported" for x in ver.check("フォンテーヌが遠目から！", "ja", fontaine).violations)
    assert ver.check("¡Fontaine desde fuera del área!", "es", fontaine).ok


def test_no_em_dash_or_middle_dot_in_a_model_line(bundle, ver):
    allowed = allowed_for(moment(player="Ibsen", target="Rasmussen"), SNAP, bundle.meta)
    for text, lang in (("Ibsen — Rasmussen.", "es"), ("Ibsen · Rasmussen.", "it"), ("ケンジ・フォンテーヌ！", "ja")):
        assert any(x.code == "punctuation" for x in ver.check(text, lang, allowed, spelled=True).violations), text


# ---------- names in Japanese ----------
def test_katakana_names_map_to_the_roster(ver):
    want = {"イブセン": "ibsen", "ラスムッセン": "rasmussen", "タヴァレス": "tavares", "タバレス": "tavares", "フォンテーヌ": "fontaine",
            "リンドクヴィスト": "lindqvist", "ペトロフ": "petrov"}
    for word, sur in want.items():
        assert ver.katakana_names(word) == {word: sur}, (word, kana_skeleton(word), skeleton(sur))
    assert ver.named("イブセンがカット、ラスムッセンへ。", "ja") == {"ibsen", "rasmussen"}
    assert ver.named("Ibsenがカット！", "ja") == {"ibsen"}  # a Latin name touching kana is still found (no spaces in Japanese)


def test_no_football_loanword_is_read_as_a_player_on_any_demo_match():
    for match_id in ("comeback-135", "comeback-7", "red_card-7", "unlucky-7", "red_card-11"):
        v = Verifier(LIB.bundle(match_id).meta)
        assert not any(v.katakana_names(w) for w in JA_LOANWORDS), match_id
        assert not v.katakana_names("ゴール！ロングボールからサイドチェンジ、ダイレクトでシュート！"), match_id


def test_a_player_outside_the_moment_is_caught_in_katakana_latin_and_turkish(bundle, ver):
    allowed = allowed_for(moment(player="Ibsen", target="Rasmussen"), SNAP, bundle.meta)
    for text, lang in (("ペトロフがカット！", "ja"), ("Petrovがカット！", "ja"), ("Petrov'un pası Rasmussen'e.", "tr")):
        v = ver.check(text, lang, allowed)
        assert any(x.code == "player_unsupported" and "Petrov" in x.detail for x in v.violations), text
    assert ver.check("イブセンからラスムッセンへ。", "ja", allowed).ok


# ---------- delivery ----------
def test_score_format_per_language():
    assert [score_said(1, 1, lang) for lang in ("es", "it", "pt", "nl", "tr", "ja")] == ["uno a uno", "uno a uno", "um a um", "één-één", "bir bir", "1対1"]
    assert shape_for_tts("1-1, y quedan unos veinte minutos.", "es") == "uno a uno, y quedan unos veinte minutos."
    assert shape_for_tts("1-1。残りはおよそ20分", "ja") == "1対1。残りはおよそ20分。"
    assert finish_line("ゴール", "ja") == "ゴール。" and finish_line("ゴール！", "ja") == "ゴール！"


# ---------- the world booth's prompt ----------
def test_world_system_names_every_solo_booth_and_the_shouts():
    for key in WORLD_KEYS:
        assert BOOTH[key].lead.name in WORLD_SYSTEM
    for shout in ("¡GOOOL!", '"GOOOL!"', "GOAL!", "Doelpunt!", "ゴール！", "1対1", "uno a uno", "um a um", "één-één", "bir bir"):
        assert shout in WORLD_SYSTEM, shout
    for never in ("No percentages", "no xG", "never a middle dot"):
        assert never.lower() in WORLD_SYSTEM.lower(), never
    assert WORLD_PROMPT_VERSION == "w3"


def test_world_prompt_gives_facts_not_english_wording(bundle):
    m = moment(player="Ibsen", target="Rasmussen", pass_type="switch", lane="right", team="Wexmoor", squad="men", arr=4385.9, named=True, xg=0.3)
    prompt = build_world_prompt(m, SNAP, bundle.meta)
    facts = json.loads(prompt.split("Facts (the only source you may use):\n")[1].split("\n\nRoom per line")[0])
    assert facts["moment"]["pass_type"] == "switch" and "arr" not in facts["moment"] and "xg" not in facts["moment"]
    assert "Across to" not in prompt and "Over to" not in prompt  # the English booth's wording never reaches the world booth
    assert re.search(r"- ja/beginner: about [\d.]+ s, at most \d+ characters", prompt)  # Japanese: characters, no words
    goal = moment(kind="score_line", left_min=19, score="1-1", team="Wexmoor Athletic")
    assert room(goal, "es/expert")[0] > room(m, "es/expert")[0]
    assert world_moment(goal).params["left_about"] == 20 == about(19) and "left_about" not in goal.params


# ---------- the runner, end to end (fake models, private cache) ----------
WORLD_LINES = {
    "duel": {"es/expert": "¡Corta Ibsen!", "it/beginner": "Ibsen intercetta.", "pt/expert": "Ibsen rouba.", "nl/beginner": "Ibsen onderschept.",
             "tr/expert": "Ibsen araya girdi.", "ja/beginner": "イブセンがカット！"},
    "shot_goal": {"es/expert": "¡GOOOL! ¡Fontaine! ¡Empata Wexmoor!", "it/beginner": "GOOOL! Fontaine! Pareggio del Wexmoor!",
                  "pt/expert": "GOOOL! Fontaine! Empata o Wexmoor!", "nl/beginner": "GOAL! Fontaine! Wexmoor maakt gelijk!",
                  "tr/expert": "GOOOL! Fontaine! Wexmoor eşitledi!", "ja/beginner": "ゴール！フォンテーヌ！ウェックスムーア、同点！"},
}
DEFAULT = {"es/expert": "Sigue la jugada.", "it/beginner": "Si gioca.", "pt/expert": "Segue o jogo.", "nl/beginner": "Er wordt gespeeld.",
           "tr/expert": "Oyun sürüyor.", "ja/beginner": "プレー続行。"}
CORE = {"en/beginner": "Won back, and seconds later it's in.", "en/expert": "Doesn't let it settle. Game on.",
        "de/beginner": "Ball gewonnen, und dann ist er drin.", "de/expert": "Direkt, und keiner geht drauf.",
        "fr/beginner": "Ballon récupéré, et c'est au fond !", "fr/expert": "En une touche, et personne ne sort !"}


def _fakes(prompts: list[str]):
    async def core(prompt: str) -> str:
        return json.dumps(CORE, ensure_ascii=False)

    async def world(prompt: str) -> str:
        prompts.append(prompt)
        kind = re.search(r"Moment kind (\w+)", prompt).group(1)
        lines = dict(DEFAULT)
        lines.update(WORLD_LINES.get(kind, {}))
        if kind == "touch":  # one channel names a player who is not in the moment: the verifier must stop it, retry and then drop it
            lines["ja/beginner"] = "ペトロフが胸で。"
        return json.dumps(lines, ensure_ascii=False)
    return core, world


def _run(bundle, tmp_path, world: bool, prompts: list[str], budget: int = 40):
    core, wcall = _fakes(prompts)
    live = LiveConfig(core, CallBudget(budget), cache_dir=tmp_path, world_call=wcall if world else None)
    return asyncio.run(Runner(bundle, "live", 1.0, False, live, 4382.0, None, 4410.0, fast=True, world=world).collect())


def test_runner_world_channels_end_to_end(bundle, tmp_path):
    prompts: list[str] = []
    msgs = _run(bundle, tmp_path, True, prompts)
    hello = msgs[0]
    assert [c["id"] for c in hello["channels"]] == list(range(12))
    says = [m for m in msgs if m["k"] == "say" and m["ch"] >= 6]
    assert says and {m["ch"] for m in says} == set(range(6, 12))
    for m in says:
        key = ALL_KEYS[m["ch"]]
        assert m["who"] == BOOTH[key].lead.name and m["src"] == "analyst"
    goal = {ALL_KEYS[m["ch"]]: m["text"] for m in says if m["kind"] == "shot_goal"}
    assert goal["es/expert"] == "¡GOOOL! ¡Fontaine! ¡Empata Wexmoor!" and goal["ja/beginner"].startswith("ゴール！")
    # the touch line naming Petrov was rejected twice on ja and is not said there (no template), the other channels say theirs
    touch = [m for m in says if m["kind"] == "touch"]
    assert touch and all(ALL_KEYS[m["ch"]] != "ja/beginner" for m in touch)
    logs = [m for m in msgs if m["k"] == "log" and (m.get("d") or {}).get("world")]
    assert any(m["step"] == "dropped" for m in logs) and any(m["step"] == "rejected" and "Petrov" in m["msg"] for m in logs)
    # one call per moment (plus the one retry), in the order the English booth called them
    kinds = [re.search(r"Moment kind (\w+)", p).group(1) for p in prompts]
    assert kinds.count("touch") == 2 and kinds.index("duel") < kinds.index("shot_goal") < kinds.index("goal_analysis") < kinds.index("score_line")
    asked = [m for m in logs if m["step"] in ("writing", "lookup")]
    assert len(prompts) == len(asked) + 1 and len({m["m"] for m in asked}) == len(asked)


def test_world_channels_leave_the_core_channels_alone_and_rerun_from_the_cache(bundle, tmp_path):
    with_world, without = [], []
    a = _run(bundle, tmp_path / "a", True, with_world)
    b = _run(bundle, tmp_path / "b", False, without)
    core_a = [(m["ch"], m["m"], m["text"]) for m in a if m["k"] == "say" and m["ch"] < 6]
    core_b = [(m["ch"], m["m"], m["text"]) for m in b if m["k"] == "say" and m["ch"] < 6]
    assert core_a == core_b and not without
    # a second run reads every world prompt from the cache: the prompts are fixed by the calling order, so the lines are identical
    again: list[str] = []
    c = _run(bundle, tmp_path / "a", True, again, budget=1)
    assert not again
    world = lambda msgs: [(m["ch"], m["m"], m["text"]) for m in msgs if m["k"] == "say" and m["ch"] >= 6]
    assert world(c) == world(a)


def test_world_needs_a_world_booth(bundle):
    async def core(prompt: str) -> str:
        return "{}"
    with pytest.raises(ValueError):
        Runner(bundle, "live", 1.0, False, LiveConfig(core, CallBudget(1)), 4382.0, None, 4410.0, world=True)
    assert len(Runner(bundle, "replay").hello()["channels"]) == 6


def test_a_comeback_story_may_not_turn_points_into_wins(bundle, ver):
    story = Moment(id=3339167, t=4239.5, clock="68", kind="story_note", voice="pbp", priority=44, ttl=8.0,
                   params={"team": "Wexmoor", "other": "Tamsworth", "facet": "comebacks", "n": 3})
    allowed = allowed_for(story, {**SNAP, "score": [0, 1]}, bundle.meta)
    for text, lang in (("Wexmoor ha ganado tres veces tras ir por detrás esta temporada.", "es"), ("O Wexmoor já virou três jogos esta temporada.", "pt"),
                       ("今季、ウェクスモアは3度逆転勝ち。", "ja"), ("Wexmoor won three times from behind this season.", "en")):
        assert any(x.code == "claim_unsupported" and "comeback_win" in x.detail for x in ver.check(text, lang, allowed).violations), text
    for text, lang in (("Wexmoor bu sezon üç kez geriden gelip puan aldı.", "tr"), ("今季、ウェクスモアは3度、負けていた試合から勝ち点を拾っています。", "ja"),
                       ("Wexmoor have taken points from losing positions three times this season.", "en"),
                       ("Tercera vez esta temporada que el Wexmoor suma puntos tras ir por detrás.", "es")):
        assert ver.check(text, lang, allowed, spelled=True).ok, (text, ver.check(text, lang, allowed, spelled=True).feedback())
    # the rule belongs to the comebacks story only: "won" stays an everyday word elsewhere
    assert ver.check("Ibsen won it back.", "en", allowed_for(moment(kind="duel", winner="Ibsen"), SNAP, bundle.meta)).ok


def test_world_continuity_is_what_the_booth_wrote_first(bundle, tmp_path):
    """A line the verifier stops is not said, but later prompts still see it as written, so a stricter rule (or a retry) never changes the
    prompts of the moments after it and their cached answers stay valid."""
    prompts: list[str] = []
    _run(bundle, tmp_path, True, prompts)
    later = [p for p in prompts if re.search(r"Moment kind (\w+)", p).group(1) == "pass_kind" and "ペトロフが胸で。" in p]
    assert later  # the ja touch line was rejected twice, yet the next pass prompt carries it in ja's continuity


def test_turkish_capital_i_on_a_roster_name_gets_the_roster_spelling(bundle):
    from matchvoice.commentary.newsroom import finish_line, roster_names
    names = roster_names(bundle.meta)
    assert "Ibsen" in names and "Rasmussen" in names
    assert finish_line("Söylemiştim! İbsen topu kaptı, bu kez hemen Rasmussen'e çapraz pas.", "tr", names) == \
        "Söylemiştim! Ibsen topu kaptı, bu kez hemen Rasmussen'e çapraz pas."
    assert finish_line("İbsen'den Rasmussen'e çapraz", "tr", names) == "Ibsen'den Rasmussen'e çapraz."
    # Turkish words keep their dotted capital, and other languages are never touched
    assert finish_line("İkinci yarıda İbsen yine kaptı.", "tr", names) == "İkinci yarıda Ibsen yine kaptı."
    assert finish_line("İbsen", "de", names) == "İbsen."


def test_turkish_capital_dotted_i_number_word_does_not_crash():
    # a live world line started with "İki"; the lookup raised KeyError and the world booth went silent
    from matchvoice.commentary import verifier as vf
    rx = vf._NUMWORD_RX["tr"]
    m = rx.search("İki dakika kaldı.")
    if m is None:
        return
    assert vf._NUMWORD_VALUE["tr"].get(m.group(1).replace("İ", "i").lower()) == 2
