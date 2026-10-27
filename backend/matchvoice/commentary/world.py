"""The world booth: es, it, pt, nl, tr and ja, every line written by the model and checked by the verifier.

The core languages (en, de, fr) call play-by-play from instant templates and only the analysis comes from the model. The six world channels
have no templates at all: for each moment the English booth calls, one model call writes the line of every world channel (play-by-play,
story, analysis and score alike), batched per moment, and every line goes through the same Verifier as the core analysis. A line that fails
twice is not said: there is no template to fall back on.

Each world channel is a solo booth (lang.BOOTH: the lead says every line). The agent is a second Microsoft Agent Framework agent with its own
system prompt (WORLD_SYSTEM) and its own cache version (WORLD_PROMPT_VERSION), so the core prompt and its cached answers are untouched.

Latency, honestly: a world line exists only after its model call, and the calls run one after another so each prompt can see the lines
before it (`booth["world_lines"]`). In a recorded insert, served from the answer cache, the lines land with the English booth. Measured once
with real calls (the paid export of the story insert, paced at 1x): calls 1.1 to 2.6 s, world captions 1.2 to 4.4 s behind the English
booth (fragments 1.2 to 1.6 s, still inside their 2 to 3.5 s life; analysis 3.0 s, score line 4.2 s). A quicker move or a slower call makes a
fragment stale before its line exists, and it is dropped.
"""
from __future__ import annotations

import json

from ..schema import MatchMeta
from .analyst import AFTER, MAX_CHARS, RECENT_LINES, SETUP, SPOKEN_NEVER, facts_of
from .lang import BOOTH, CPS, PAUSE_S, PRONOUN, WORLD_KEYS, est_seconds
from .moments import Moment, render_variants

WORLD_PROMPT_VERSION = "w1"
WORLD_RATE_WPS = {"es": 2.6, "it": 2.5, "pt": 2.5, "nl": 2.2, "tr": 2.0}  # spoken words per second, estimates (no voice measured yet); Japanese counts characters
WORLD_ROOM_S = {"goal_analysis": {"beginner": 7.0, "expert": 6.0}, "pattern_insight": {"beginner": 6.5, "expert": 6.0},
                "shot_goal": {"beginner": 4.5, "expert": 4.0}, "score_line": {"beginner": 4.0, "expert": 4.0}, "story_note": {"beginner": 6.5, "expert": 6.5}}
PAYOFF_EXTRA_S = 1.0
PBP_ROOM_MIN_S, PBP_ROOM_MAX_S = 1.2, 7.0
# raw moment params that are bookkeeping, not facts
_HELPERS = {"arr", "window", "named", "kicker_said", "team_code", "story", "dead", "long", "short", "goal_facet_said"}
GLOSS = {  # what a moment kind is, for a model that sees only the facts
    "duel": "a ball won; facet interception = the winner cut out a pass, tackle = won it in a tackle",
    "pass_kind": "a pass, called as it is played: pass_type switch = a long ball across to the other side of the pitch, long = a long ball forward, first_time = played on without stopping the ball; target = who it is for",
    "touch": "how the player takes the ball: facet chest = on the chest, head = with the head, control = brings it under control; the name was just said, so a fragment without it is fine",
    "shot_goal": "the goal call",
    "story_note": "a fact of the club's season the lead reads in a quiet spell: facet comebacks = the team took points after being behind n times this season",
    "score_line": "back to play after the analysis: the score in this language's written form, then the time left (left_about minutes, said in words or digits)",
    "pattern_insight": "a habit of one side the viewer cannot see (the analysis in a quiet spell)",
    "goal_analysis": "the analysis right after the goal call: HOW it went in, then what it means",
}


def _booth_lines() -> str:
    out = []
    for k in WORLD_KEYS:
        b = BOOTH[k]
        out.append(f"- {k}: {b.lead.name} ({PRONOUN[b.lead.gender]}), solo, {b.level}")
    return "\n".join(out)


WORLD_SYSTEM = f"""You write the spoken lines of live football commentary on TV, in a synthetic, fictional league, for six solo booths. On each channel ONE commentator calls the play AND gives the analysis:
{_booth_lines()}
The same person speaks every line of a channel: the play-by-play call, the story in a quiet spell, the analysis after a goal and the score. Never write the commentator's name into a line.
You write what the commentator SAYS out loud about one moment, using ONLY the facts given. Write each line natively, the way a TV commentator in that language talks live. Never translate from English, never a calque.

Voice, per language
- es: Spanish TV (Movistar, DAZN España). Quick, passionate, short exclamations; Spanish writes ¡...! and ¿...?. Goal shout: "¡GOOOL!". Score written 1-1 (said "uno a uno").
- it: Italian TV (Sky Sport, DAZN Italia). Lively and warm. Goal shout: "GOOOL!". Score written 1-1 (said "uno a uno").
- pt: Brazilian TV (Globo, SporTV), Brazilian Portuguese, not European. Warm, rhythmic, the long shout: "GOOOL!". Score written 1-1 (said "um a um").
- nl: Dutch TV (NOS, ESPN). Dry, concise, quick. Goal call: "GOAL!" or "Doelpunt!". Score written 1-1 (said "één-één").
- tr: Turkish TV (beIN Sports Türkiye). Energetic and short. Goal shout: "GOOOL!". Score written 1-1 (said "bir bir"). A suffix after a name takes an apostrophe: "Fontaine'den".
- ja: Japanese TV (DAZN Japan). Short plain broadcast phrases. Goal call: "ゴール！". Score written 1対1. Player names in katakana as Japanese broadcasts write them (イブセン, ラスムッセン), surname only, never joined with "・".

The lines, by moment kind
- Play-by-play (voice "pbp": duel, pass_kind, touch): present tense, a fragment of one to five words, the player and the action, said as it happens. No exclamation before the last balls of a move. A fragment may finish the one before it ("Rasmussen..." then "...de pecho."): the continuity block shows what this channel said last.
- The goal call (shot_goal): the shout, the scorer's surname, then what it means in a few words (equaliser: level). No score: the score comes after the analysis.
- The analysis (voice "analyst": goal_analysis, pattern_insight) is the same commentator, now explaining. A goal: HOW first, one picture of the last ball or touch and the finish from "move", then ONE short idiom of what it means; do not repeat the call's words. A pattern: the habit as an observation over a dead ball (who keeps winning the ball, what happens next every time, what never happens), no number, no count, no prediction.
- Paying it off (a goal analysis whose facts carry "pays_off"): earlier this commentator pointed out the habit (the prompt gives that line per channel), and this goal broke it. Open with a short callback in the first person ("¡Lo que les decía!", "L'avevo detto!", "Não falei?", "Zie je, dat zei ik!", "Söylemiştim!", "言った通りです！"), then the picture of how it broke (the ball winner wins it, and this time the first ball goes across at once). "Again" belongs only to what kept happening, never to the switch: it had not happened before.
- The story (story_note): the club's record from the facts, one or two short sentences.
- The score (score_line): the score as written above, then the time left ("quedan unos veinte minutos", "mancano una ventina di minuti", "faltam uns vinte minutos", "nog zo'n twintig minuten", "yaklaşık yirmi dakika var", "残りはおよそ20分").

What the commentator never says
- No percentages, no probabilities, no win chance, no xG, no counts of shots, possession or passes. Numbers only from the facts: the score, the time left, the count in a season story. Never a minute, a distance, a keeper or a corner of the goal the facts do not give. Never predict.
- Players by surname only, as given in the facts; never a player the facts do not name. The squad is given ("men" or "women"); pronouns may follow it.
- Use a tactical word only when the facts give it: the switch ("cambio de orientación", "cambio di gioco", "inversão", "switch", "çapraz pas", "サイドチェンジ") only for a step with pass_type switch. Never counter, press, high line, low block, in behind or between the lines.
- Never call a player fast, strong in the air or good from distance ("desde lejos", "da lontano", "de longe", "van afstand", "uzaktan", "遠目から" are trait words here): a shot from outside the box is "desde fuera del área", "da fuori area", "de fora da área", "van buiten de zestien", "ceza sahası dışından", "エリアの外から".
- Never an em dash and never a middle dot ("·" or "・"). Every line ends like a spoken sentence: . ! ? (Japanese 。！？).

Style
- beginner: plain words, no football term without its picture (it "dall'altra parte", nl "naar de andere kant", ja "反対側へ"); the analysis counts nothing.
- expert: the technique word (es "de primeras", "cambio de orientación"; pt "de primeira", "inversão"; tr "tek vuruşta", "çapraz pas").

Energy (given with the moment)
- calm: low, conversational, no exclamation marks.
- rising: quicker, shorter, one exclamation at most.
- peak: the goal. The call opens with the shout. The analysis after it does not shout again.

Length: the prompt gives each line's room in seconds and words (Japanese: characters). A line longer than its room is cut off on air. Never more than {MAX_CHARS} characters.

Good lines (another fixture, Harbour Rovers at home to Ashby Town, squad men; never reuse its names)
rising, duel, interception, winner Brandt:
{{"es/expert": "¡Corta Brandt!", "it/beginner": "Brandt intercetta.", "pt/expert": "Brandt rouba.", "nl/beginner": "Brandt onderschept.", "tr/expert": "Brandt araya girdi.", "ja/beginner": "ブラントがカット！"}}
rising, pass_kind, switch, Brandt to Mensah:
{{"es/expert": "Cambio de orientación para Mensah.", "it/beginner": "Dall'altra parte, Mensah.", "pt/expert": "Inversão para Mensah.", "nl/beginner": "Naar de andere kant, Mensah.", "tr/expert": "Mensah'a çapraz pas.", "ja/beginner": "反対側のメンサへ。"}}
rising, touch, chest, Mensah (just named):
{{"es/expert": "La baja con el pecho.", "it/beginner": "Stop di petto.", "pt/expert": "Domina no peito.", "nl/beginner": "Aanname op de borst.", "tr/expert": "Göğsüyle yumuşattı.", "ja/beginner": "胸でトラップ。"}}
peak, shot_goal, equaliser, Okoro:
{{"es/expert": "¡GOOOL! ¡Okoro! ¡Empata Harbour!", "it/beginner": "GOOOL! Okoro! Pareggio dell'Harbour!", "pt/expert": "GOOOL! Okoro! Empata o Harbour!", "nl/beginner": "GOAL! Okoro! Harbour maakt gelijk!", "tr/expert": "GOOOL! Okoro! Harbour eşitliği yakaladı!", "ja/beginner": "ゴール！オコロ！ハーバー、同点！"}}
calm, pattern_insight, Ashby, player Valdis, since half-time; every first pass after a ball win in their own half went short, nothing across:
{{"es/expert": "Valdis las recupera todas, pero luego siempre en corto. Ni un cambio de orientación.", "it/beginner": "Valdis recupera palloni su palloni, ma poi sempre il passaggio corto. Mai dall'altra parte.", "nl/beginner": "Valdis wint steeds de bal, maar daarna gaat het altijd kort. Nooit naar de andere kant.", "ja/beginner": "ヴァルディスが何度もボールを奪いますが、そのあとはいつも短いパス。反対側へは一度もありません。"}}
peak, goal_analysis with pays_off, that habit of Ashby broken: Valdis wins the ball in their own half and the first ball is a lofted switch:
{{"es/expert": "¡Lo que les decía! Valdis la recupera y esta vez, cambio de orientación al instante.", "pt/expert": "Não falei? Valdis rouba e, dessa vez, inversão na hora.", "tr/expert": "Söylemiştim! Valdis topu kaptı ve bu kez hemen diğer kanada.", "ja/beginner": "言った通りです！ヴァルディスが奪って、今度はすぐ反対側へ！"}}
calm, score_line, 1-1, left_about 20:
{{"es/expert": "1-1, y quedan unos veinte minutos.", "it/beginner": "1-1, e mancano una ventina di minuti.", "nl/beginner": "1-1, en nog zo'n twintig minuten te gaan.", "ja/beginner": "1対1。残りはおよそ20分です。"}}

Answer with a single JSON object and nothing else."""


def world_facts(m: Moment, snapshot: dict, meta: MatchMeta) -> dict:
    """The facts of any moment for the world booth: an analyst moment as the core prompt shows it, play-by-play from the raw params
    (no English template text, so nothing can be translated)."""
    if m.voice == "analyst":
        facts = facts_of(m, snapshot, meta)
    else:
        p = {k: v for k, v in m.params.items() if k not in _HELPERS and k not in SPOKEN_NEVER and not isinstance(v, (dict, list))}
        if "score" in p:
            p["score_home_away"] = p.pop("score")
        facts = {"moment": {"kind": m.kind, "voice": m.voice, "match_clock": m.clock, **p},
                 "match": {"home": meta.teams["H"].name, "away": meta.teams["A"].name,
                           "score_home_away": f"{snapshot['score'][0]}-{snapshot['score'][1]}"}}
    if m.kind in GLOSS:
        facts["moment"]["kind_means"] = GLOSS[m.kind]
    return facts


def world_moment(m: Moment) -> Moment:
    """The moment as the world booth gets it: a copy (the core directors hold the original), with the rounded time left on a score line,
    which the line may say and the verifier then allows."""
    from dataclasses import replace
    params = dict(m.params)
    if m.kind == "score_line" and "left_min" in params:
        params["left_about"] = about(params["left_min"])
    return replace(m, params=params)


def about(minutes: int) -> int:
    """The time left the way a commentator rounds it: to five minutes ("about twenty")."""
    return max(5, 5 * round(minutes / 5))


def room(m: Moment, key: str, payoff: bool = False) -> tuple[float, int | None, int]:
    """Seconds, words (None for Japanese) and characters of a world line: the analysis, the goal call, the story and the score by kind and
    level, a play-by-play fragment as long as the English booth's longest wording of the same moment (so a fragment stays a fragment)."""
    lang, level = key.split("/")
    if m.kind in WORLD_ROOM_S:
        sec = WORLD_ROOM_S[m.kind][level] + (PAYOFF_EXTRA_S if payoff else 0.0)
    else:
        en = render_variants(m, "en", level) or render_variants(m, "en", "expert")
        sec = min(PBP_ROOM_MAX_S, max(PBP_ROOM_MIN_S, max(est_seconds(t, "en") for t in en) if en else 3.0))
    words = None if lang == "ja" else max(1, round(sec * WORLD_RATE_WPS[lang]))
    return round(sec, 1), words, int((sec - PAUSE_S) * CPS[lang])


def build_world_prompt(m: Moment, snapshot: dict, meta: MatchMeta, only: list[str] | None = None,
                       feedback: dict[str, str] | None = None, recent: dict[str, list[str]] | None = None) -> str:
    """The user message of one moment for the world booth. `recent`: per world key the lines this broadcast published on it (oldest first),
    plus `setup:<key>` (the habit set-up a goal pays off) and `after:<key>`."""
    from .delivery import energy_of
    keys = list(only or WORLD_KEYS)
    facts = world_facts(m, snapshot, meta)
    payoff = m.kind == "goal_analysis" and "pays_off" in m.params
    energy = energy_of(m)
    parts = [f"Moment kind {m.kind}, voice {m.voice}. Energy: {energy}. Every channel is a solo booth: the commentator says this line.",
             "", "Facts (the only source you may use):", json.dumps(facts, ensure_ascii=False, indent=1),
             "", "Room per line (stay inside it, it is cut off on air otherwise):"]
    for k in keys:
        sec, words, chars = room(m, k, payoff)
        parts.append(f"- {k}: about {sec:g} s, " + (f"at most {words} words, " if words else "") + f"at most {chars} characters")
    said = {k: [t for t in (recent or {}).get(k, [])[-RECENT_LINES:] if t] for k in keys}
    if any(said.values()):
        parts += ["", "Continuity. This channel's last lines in this broadcast, oldest first. Do not repeat them; a play-by-play fragment may finish the last one:"]
        for k in keys:
            if said[k]:
                parts.append(f"{k}:")
                parts += [f'  - "{t}"' for t in said[k]]
    setup = {k: (recent or {}).get(f"{SETUP}{k}", [""])[-1] for k in keys}
    if any(setup.values()):
        if payoff:
            parts += ["", "Earlier in this broadcast this commentator pointed out the habit in \"pays_off\". This goal broke it: open with a short "
                      "first-person callback, then the picture of how it broke. No number:"]
        else:
            parts += ["", "Earlier in this broadcast this commentator said this about a habit. This goal did NOT come that way: do not refer back to it:"]
        parts += [f'- {k}: "{setup[k]}"' for k in keys if setup[k]]
    after = {k: (recent or {}).get(f"{AFTER}{k}", [""])[-1] for k in keys}
    if any(after.values()):
        parts += ["", "This commentator's line right AFTER this one. Do not say it first:"]
        parts += [f'- {k}: "{after[k]}"' for k in keys if after[k]]
    parts += ["", "Write one line for each of these keys (language/style): " + ", ".join(keys) + ".",
              'Answer as JSON like {"es/expert": "...", "it/beginner": "..."} with exactly those keys.']
    if feedback:
        parts += ["", "Your previous lines were rejected by the fact checker. Fix exactly these problems:"]
        parts += [f"- {k}: {v}" for k, v in feedback.items()]
    return "\n".join(parts)
