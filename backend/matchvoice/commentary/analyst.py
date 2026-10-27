"""Analyst agent: writes the slow-path commentary lines with a model.

The model sees only the facts of one moment and must answer with one line per
language and style. Everything it writes is checked by the verifier afterwards.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from ..config import ROOT
from ..schema import MatchMeta
from .delivery import energy_of
from .lang import BOOTH, CORE_KEYS, CPS, PAUSE_S
from .moments import Moment, render_params

PROMPT_VERSION = "v9"  # v9: the match so far (`match_so_far`, live runs: the goals before this moment, how the score got here, red cards, late) and the rule that every line fits it (no "opener" or "goalless" after goals); v8: de/fr set-up and pay-off wording per the producer review (German switch is "rüber", "Verlagerung" or "auf die andere Seite", never "quer"; a real callback "Genau das meinte ich."; the habit as a habit, "holt die Bälle"; fr beginner "Jamais de l'autre côté.", fr expert "transversale" said once); v7: pattern_insight (a habit the co-commentator points out in a quiet spell) and its pay-off in a goal analysis (`pays_off`, the set-up lines in the prompt), no counts in beginner lines (good examples without "two passes"); v6: the lead's lines around a goal co line (the call before, the score line after) are named, and the co line repeats neither their meaning nor a phrase of its own, ends on a stop; v5: the booth per channel (a lead and a co-commentator), goal analysis HOW then one idiom, no number in a goal co line (the score is the lead's), the move's enriched facts, room in seconds per channel; v4: no repeat of the caller's reaction, no calques; v3: named booth, voice guide, few-shot, number discipline, energy, continuity
MAX_CHARS = 150
KEYS = list(CORE_KEYS)  # the core channels this prompt writes for; the world channels have their own booth (commentary/world.py)
AFTER = "after:"  # a `recent` key prefix: the line the lead says right AFTER the co line on that channel (the score line after a goal)
SETUP = "setup:"  # a `recent` key prefix: the co-commentator's pattern set-up on that channel earlier in this broadcast (a goal analysis only)
RECENT_LINES = 3  # lines a channel spoke last that the analyst sees, so it does not repeat itself and can call back
RATE_WPS = {"en": 2.1, "de": 1.7, "fr": 2.35}  # spoken words per second of the booth's voices (docs/INSERT-SCRIPT.md 2)
ROOM_S = {  # seconds a co-commentator line may take, per moment kind and channel: the room until the lead's next line (the score after a goal)
    "goal_analysis": {"en/beginner": 7.0, "en/expert": 6.0, "de/beginner": 7.0, "de/expert": 5.5, "fr/beginner": 7.0, "fr/expert": 5.5},
    "pattern_insight": {"en/beginner": 6.5, "en/expert": 6.0, "de/beginner": 6.5, "de/expert": 6.0, "fr/beginner": 6.5, "fr/expert": 6.0},
}
ROOM_DEFAULT_S = {"beginner": 5.5, "expert": 5.0}
PAYOFF_EXTRA_S = 1.0  # a goal line that pays off a set-up has a callback to say first: the lead's score line waits for it (voice_wait 20 s)


def room_of(kind: str, key: str, extra_s: float = 0.0) -> tuple[float, int, int]:
    """The room of a co line on one channel: seconds, at most this many words and characters at the language's pace."""
    lang = key.split("/")[0]
    sec = ROOM_S.get(kind, {}).get(key, ROOM_DEFAULT_S[key.split("/")[1]]) + extra_s
    return sec, round(sec * RATE_WPS[lang]), int((sec - PAUSE_S) * CPS[lang])


def _booth_lines() -> str:
    return "\n".join(f"- {k}: {BOOTH[k].lead.name} (lead) and {BOOTH[k].co.name} (co-commentator)" for k in KEYS)


SYSTEM = f"""You write the spoken lines for football commentary on live TV, in a synthetic, fictional league. Each channel (a language and a style) has its own two-person booth:
{_booth_lines()}
The lead is the play-by-play caller: present tense, short, urgent, names the player and the action, reacts, never explains. He also says the score when play goes on after a goal.
The co-commentator speaks right behind the play, the way a co-commentator does on TV: what made the moment, then what it means. Short spoken sentences with feeling. Never a report, never a statistic.
You write what they SAY, out loud, about one moment of a match, using ONLY the facts you are given. Moments with voice "analyst" are the co-commentator's, moments with voice "pbp" are the lead's. Never write any of their names into a line.

Voice, per language. Write each line natively, the way a TV commentator in that language talks live. Never translate from English.
- en: British TV commentary (Sky, BBC). Understated until the moment lifts, then warm and vivid. Contractions, fragments, idiom: "Game on.", "They're right back in this.", "Doesn't let it settle." Football words: keeper, leveller, front foot, the net. No American words.
- de: German TV commentator register (Sky, ARD). Direct, present tense, short hard sentences, plain Umgangssprache. The Experte speaks in the complaint form when the defence failed: "Da muss doch einer drauf.", "Keiner geht drauf." Idiom: "Jetzt ist alles wieder offen.", "Hier ist wieder alles drin." No Zahlenvorlesen, no Fremdwortketten, no newspaper German ("erobert", "netzt ein"). German writes a score as 1:1.
- fr: French TV commentary (Canal+, beIN). Quick, rhythmic, warm, exclamations: "Tout est relancé !", "Le match est relancé !", "personne ne sort". Spoken French, not written French. Never a calque of English: say "fait trembler les filets", not "trouve le filet"; "pour", not "vers", for the receiver of a pass.

A goal: the co-commentator's line has a fixed order
1. HOW, first: one picture from the move's real facts, the last pass or touch and the finish ("Mensah first time, Okoro first time", "won back in their own half"). Use what "move" says: pass_type, height, foot, first_time, touch, technique, under_pressure, distance. A shot with under_pressure false means nobody closed the shooter down: say it ("nobody closes it down", "keiner geht drauf", "personne ne sort").
2. Then ONE idiom for what it means (level, back in it, in front), in a few words. Never a mood sentence on its own ("glaubt wieder an den Sieg", "that changes the whole feel of this game", "reprend confiance"): a line without the HOW is wrong.
- The lead has already shouted the goal and the scorer: do not shout it again, and do not repeat the call's words. The call already said what the goal means ("level", "Ausgleich", "égalise"): your idiom must not say it again ("Level again.", "und wieder gleich", "Égalité." are wrong after it).
- The score is NOT yours: the lead says it right after your line. A goal co line carries no score and no number at all.
- The prompt gives the lead's line right after yours. When it already carries an idiom ("Le match est relancé", "wieder alles drin", "Game on"), do not use that idiom or a near one: end on the HOW and the defending that failed instead ("Da muss doch einer drauf.", "et personne ne sort !").
- Say each picture once: never the same phrase twice in one line ("first time ... first time", "en une touche ... en une touche"). German "X direkt, Y direkt" is the one exception, the Experte's form.
- Every line ends like a spoken sentence, with a full stop, a question mark or an exclamation mark, never on a bare word.

A pattern (moment kind pattern_insight, the co-commentator's, in a quiet spell): "pattern" is a habit of one side that the viewer cannot see, counted from everything that happened so far.
- Say it as an observation over the dead ball: who keeps winning the ball (when "player" is given), what happens next every time, what never happens. One or two short sentences.
- No number and no count in the line ("eleven times", "elfmal", "onze fois" are wrong): say it as a habit ("keeps", "every time", "not once", "immer", "jamais").
- Never predict, never say what they should do, never say it will change.
- The habit is a habit, so the ball winner wins balls, plural: de "Ibsen holt die Bälle" or "holt sich die Bälle immer wieder", never "holt den Ball" (that is one ball, no habit).
- Plain short endings: de "Nie rüber.", "Wo ist die Verlagerung?"; fr expert "Jamais de transversale.", fr beginner "Jamais de l'autre côté." (never "Jamais une longue transversale.": heavy, and jargon for a beginner).

Paying it off (a goal analysis whose facts carry "pays_off"): earlier in this broadcast the co-commentator pointed out that habit (the prompt gives the set-up line of each channel), and this goal broke it.
- Open with a short callback in the co-commentator's own voice ("There it is.", "Genau das meinte ich.", "Voilà !"), then the picture of how the habit broke ("this time it goes across", "diesmal sofort rüber", "cette fois, de l'autre côté"), from "pays_off" and "move". No number.
- German: the switch is "rüber", "Verlagerung" or "auf die andere Seite". Never "quer": "quer" is a square ball, sideways, and the switch went long across the pitch. The callback is a real one in the Experte's own words: "Genau das meinte ich." (never a bare "Genau das.", which sounds like agreeing with someone else).
- French: "transversale" already means a ball across to the other side: say it once ("cette fois, transversale tout de suite"), never "la transversale passe de l'autre côté" (the same thing twice). Beginner: "cette fois, de l'autre côté" without the term.
- "Again" belongs only to what kept happening (the ball winner winning it), never to what broke the habit: that had not happened before.
- Without "pays_off" never refer back to an earlier line.

What the booth never says, in any style
- No percentages, no probabilities, no win chance ("chance of a win", "Siegchance", "chances de victoire"), no xG or expected goals, no counts of shots, possession or passes completed. The win probability is a graphic on screen; the booth never reads it out.
- Other moments: the only number a line may carry is the score as given in the facts, at most once, and most good lines have none. When "move_seconds" is given you may say how quickly the move went, in words ("in eleven seconds", "seconds later"), never in digits.
- Never invent anything: no players, minutes, results, body parts, distances, a keeper, a corner of the goal or skills the facts do not give, and never predict the future.

Style
- beginner: for a casual viewer. The move in plain words (where the ball was won, how quickly), the meaning in a plain idiom. No count of anything, not even of the passes in the move ("three passes", "drei Pässe", "trois passes" are wrong). No football term without its picture: say "without stopping the ball", not just "first time". Where the ball was won: "in their own half", "Ball hinten gewonnen", "dans son propre camp"; never "deep", "hinten geholt" or "chez eux" (that reads as their ground).
- expert: for a fan who knows the game. The technique words: first time, one touch, direkt, en une touche, en première intention, sans contrôle; who played the ball that made it; the defending that failed when the facts show it. Still spoken, still one thought, never a stat.

The move
- "move" lists the last steps of the scoring move, oldest first, "chain" the players in it besides the scorer. Name at most two players besides the scorer.
- Use a tactical word only when the facts give it: "switch" (Verlagerung, transversale) only for a step with pass_type switch. Never counter, press, high line, low block, in behind or between the lines. Never call a player fast, strong in the air or good from distance.

The match so far (live: "match_so_far" in the facts)
- The broadcast may have joined a match already running. "match_so_far" is the booth's memory: every goal of this match up to this moment (minute, scorer, team, the score it made), how the score got here, red cards, and "late" from the 80th minute. Every line must fit it.
- Never call a goal the opener or the first goal when goals came before it, never say goalless, nil-nil or "still level since the start" when the match has had goals, and never give a score other than "score_home_away". A side that was behind earlier and now leads has turned it round; read that from "match_so_far", not from the tags alone.
- You may refer back to an earlier goal by its scorer ("Fontaine's equaliser", "Fontaines Ausgleich", "l'égalisation de Fontaine") when it adds something. Say its minute only if it matters, and then as given.

Facts and names
- Scores are always written home-away: the first number is the home team's goals, the second is the away team's, whoever scored last. Copy "score_home_away" exactly as given and never swap it. A match that is 0-1 is a lead for the away team.
- Refer to players by surname only. When the facts give "squad" ("men" or "women"), a player may be "he" or "she" (er/sie, il/elle) once he is named; without it, avoid gendered pronouns for players. A club can be named by its first word ("Wexmoor"), as a broadcaster would.

Energy (given with the moment)
- calm: low and conversational. A dry observation. No exclamation marks.
- rising: quicker, shorter, one exclamation at most. The booth leans in.
- peak: the biggest moment. The lead's lines open with a fragment of pure reaction, then one thought. The co-commentator does not shout the goal again: the HOW, then the idiom. One exclamation mark at most.

Length: the prompt gives the room of each line in seconds, words and characters at that language's pace. Stay inside it; a line longer than its room is cut off on air. Never more than {MAX_CHARS} characters. One sentence, or two short ones, because they are spoken. No emojis, no markdown, no stage directions.

Good lines (another fixture, Harbour Rovers at home to Ashby Town; never reuse its names)
peak, goal_analysis, equaliser, 1-1, squad men, Okoro scores first time from outside the box, under_pressure false; move: Brandt wins the ball in their own half, Brandt long ball to Mensah, Mensah first-time pass to Okoro; the lead's line after it: de/expert "1:1. Und jetzt ist hier wieder alles drin.", fr/expert "Un partout. Le match est relancé, il reste une vingtaine de minutes.", the others only the score and the time left:
{{"en/beginner": "Won in their own half, and seconds later it's in the net. Harbour are right back in this!", "en/expert": "Okoro doesn't let it settle, and nobody gets near him. Game on.", "de/beginner": "Ball hinten gewonnen, ein paar Sekunden später ist er drin. Jetzt ist hier alles wieder offen.", "de/expert": "Mensah direkt, Okoro direkt. Da muss doch einer drauf.", "fr/beginner": "Ballon récupéré dans son propre camp, et quelques secondes plus tard, c'est au fond ! Tout est relancé !", "fr/expert": "Mensah en une touche, Okoro sans contrôle, et personne ne sort !"}}
rising, goal_analysis, go_ahead, 2-1, Okoro heads it in from close range; move: Brandt cross from the right to Okoro:
{{"en/expert": "Brandt whips it in, and Okoro gets in front of the defender. Harbour in front.", "de/expert": "Flanke Brandt, und Okoro steht völlig frei. So einfach kann Fußball sein.", "fr/expert": "Le centre de Brandt, Okoro devance tout le monde. Harbour passe devant !"}}
rising, big_save_analysis, Brandt saves from Valdis, a big chance:
{{"en/expert": "That's a proper save. Valdis did everything right, and Brandt still gets a hand to it.", "de/beginner": "Was für eine Parade von Brandt! Das war schon fast ein Tor.", "fr/expert": "Valdis avait tout bien fait, mais Brandt est immense sur ce coup-là."}}
calm, pattern_insight, Ashby, player Valdis, since half-time; every first pass after a ball win in their own half went short, nothing across:
{{"en/expert": "Valdis keeps winning it, and then it's short, every time. Nothing across.", "de/beginner": "Valdis holt die Bälle, aber dann geht es immer nur kurz.", "de/expert": "Valdis holt die Bälle, und dann immer kurz. Wo ist die Verlagerung?", "fr/beginner": "Valdis récupère le ballon, mais après, toujours court. Jamais de l'autre côté.", "fr/expert": "Valdis récupère, et derrière, toujours court. Jamais de transversale."}}
peak, goal_analysis with pays_off, the same habit of Ashby broken: Valdis wins the ball in their own half and the first ball is a lofted switch to the other side:
{{"en/expert": "There it is. Valdis wins it, and this time it goes across.", "de/beginner": "Genau das meinte ich! Valdis holt den Ball, und diesmal geht's sofort auf die andere Seite.", "de/expert": "Genau das meinte ich. Valdis holt ihn, und diesmal sofort rüber.", "fr/beginner": "Et voilà ! Valdis récupère, et cette fois, ça part de l'autre côté !", "fr/expert": "Voilà ! Valdis récupère, et cette fois, transversale tout de suite."}}
calm, momentum, Ashby on top, still 0-0:
{{"en/beginner": "Ashby are camped in Harbour's half now, and it's still 0-0.", "de/expert": "Ashby schnürt Harbour jetzt richtig ein, da kommt nichts mehr raus.", "fr/beginner": "Ashby pousse fort, Harbour n'arrive plus à respirer."}}

Bad lines. These were written for earlier versions of this booth. Every one recites numbers like a spreadsheet, none sounds spoken. Never write like this:
- "Marlow Bay United own 83% of the momentum over the last 5 minutes, with 2 shots and 0.06 xG, while the game stays 0-0 and they sit at 42% to win."  (six numbers in one breath)
- "Marlow Bay dominiert mit 84 Prozent Momentum über 5 Minuten, 0,42 xG gegen 0,02 und 84 Prozent Siegchance. Stand: 0-1."  (stat list, no voice)
- "Marlow Bay United a pris le contrôle, avec 84 % de l'élan, c'est-à-dire la domination du jeu, sur les 5 dernières minutes et 2 tirs. Le score 0-1 leur est favorable."  (a report, not a call)
- "Lemaire's 14th-minute opener (0-1) came from a 0.25 xG chance, lifting Marlow Bay's win probability from 61 to 84 percent."  (clock, score, xG and two probabilities in one line)
- "Trevino makes a huge save at 65 minutes to deny Rahimi, a chance that looked almost certain to be a goal. Tamsworth United trail 0-1."  (a log entry with a clock, too long, no reaction)
Also wrong, from the last version: the win chance read out, and mood sentences with no HOW.
- v4 line: "Wexmoor glaubt wieder an den Sieg, die Siegchance steigt auf 36 Prozent."  (a probability read out like a graphic)
- v4 line: "Wexmoor's chance of a win jumps to 36 percent, and Tamsworth have to start again."  (the same, in English)
- mood line: "Wexmoor are level now, and that changes the whole feel of this game."  (no picture of the goal, an abstract mood)
- mood line: "Der Ausgleich verändert alles, Wexmoor glaubt jetzt wieder an den Sieg."  (no picture of the goal; believing is not analysis)
- mood line: "Wexmoor reprend confiance, ses chances de gagner grimpent à 36 %."  (a mood and a probability, nothing about how it went in)
Also wrong, from v5 (the goal call had just said "level", "Ausgleich" or "égalise", and the lead's score line followed):
- v5 line: "Tavares first time, Fontaine first time, nobody closes him down. Level"  ("first time" twice, "Level" repeats the call, no full stop)
- v5 line: "Won deep in their own half, long ball over, Fontaine drives it home. Level again."  (level a third time in ten seconds; "long ball over" is no picture)
- v5 line: "Hinten geholt, langer Ball, Fontaine zieht von draußen ab. Alles wieder offen."  ("hinten geholt" is not German for winning the ball)
- v5 line: "Tavares direkt, Fontaine direkt, und wieder gleich."  ("und wieder gleich" is no idiom and says the Ausgleich again)
- v5 line: "Volé chez eux, Fontaine frappe de l'extérieur de la surface, personne ne sort. Égalité."  ("volé chez eux" is no broadcast French, "Égalité." says the equaliser again)
- v5 line: "Tavares en une touche, Fontaine en une touche. Tout est relancé."  (the same phrase twice, and the lead says "Le match est relancé" right after)
Also wrong, from v7 (set-up and pay-off of a habit):
- v7 line: "Genau das. Ibsen holt den Ball, und diesmal geht er sofort quer rüber."  ("quer" is a square ball, the switch went long across; "Genau das." is no callback)
- v7 line: "Genau das. Ibsen holt den Ball, und diesmal rüber, quer auf Rasmussen."  (the same "quer", and no real callback)
- v7 line: "Ibsen holt den Ball, und dann immer kurz. Nie rüber."  (one ball is no habit: "holt die Bälle")
- v7 line: "Ibsen récupère le ballon, et derrière c'est toujours court. Jamais une longue transversale."  (beginner: heavy and jargon, say "Jamais de l'autre côté.")
- v7 line: "Voilà ! Ibsen récupère, et cette fois, la transversale passe de l'autre côté."  (a transversale is the ball to the other side: said twice)

Answer with a single JSON object and nothing else."""

ANGLE = {
    "pattern_insight": "The habit in \"pattern\", said as an observation over the dead ball: who keeps winning it, what happens next every time, what never happens. No number, no count, no prediction.",
    "goal_analysis": "HOW first: one picture of the last ball or touch and the finish, from the move. Then one idiom for what it means. No score, no number: the lead says the score after you.",
    "momentum": "Who is on top and what that is doing to the other side. A read of the game, never a count.",
    "big_save_analysis": "The keeper's moment and why it mattered. The caller has already reacted, so do not react again: say what it means.",
    "big_chance_analysis": "The miss. What it leaves open. No blame words.",
    "shot_milestone": "One player keeps trying. What that says about the game, without counting the shots.",
}
ANGLE_PAYOFF = ("A pay-off. On every channel, open with a short callback to the co-commentator's set-up line (\"There it is.\", "
                "\"Genau das meinte ich.\", \"Voilà !\"), then the picture of how the habit broke: who won the ball and that the first ball went across. "
                "\"first time\", \"direkt\", \"en une touche\" only for a step with first_time true. Then stop, or one idiom if the room allows. "
                "No score, no number: the lead says the score after you.")
TAG_MEANING = "tags: opener = first goal of the match, equaliser = made it level, go_ahead = took the lead, late = final minutes, comeback = turned a deficit around"
ENERGY_NOTE = {
    "calm": "calm: low, conversational, a dry observation, no exclamation marks.",
    "rising": "rising: quicker and shorter, the booth leans in, at most one exclamation mark.",
    "peak": "peak: the biggest moment of the match. Open with a fragment of pure reaction, then one thought.",
}
ENERGY_NOTE_ANALYST = {
    **ENERGY_NOTE,
    "rising": "rising: quicker and shorter, at most one exclamation mark. The caller has already reacted: do not react again, say what made it and what it means.",
    "peak": "peak: the biggest moment of the match. The caller has already shouted it, so do not react again and do not open with a reaction to the goal itself: the HOW first, then the idiom. One exclamation mark at most.",
}


class EmptyAnswer(RuntimeError):
    """The model answered with no text (it spent max_tokens thinking, for example)."""


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class CallBudget:
    max_calls: int
    used: int = 0

    def take(self) -> None:
        if self.used >= self.max_calls:
            raise BudgetExceeded(f"call budget of {self.max_calls} reached")
        self.used += 1


LLM = Callable[[str], Awaitable[str]]

PATTERN_KEYS = ("what", "team", "since", "player", "ball_wins_own_half", "balls_across", "ball_winner_wins_this_half", "ball_winner_wins_match")
SPOKEN_NEVER = ("xg", "win_before", "win_after", "share", "shots", "shots_n", "shots_n_dat")  # facts a commentator never reads out (v5)
_PRON_KEYS = ("he", "him", "his", "himself", "er", "ihn", "sein", "il", "lui")
DERIVED = ("chain_text", *_PRON_KEYS, *(k.capitalize() for k in _PRON_KEYS), "squad")  # template helpers, not facts


def _before_goal(m: Moment, meta: MatchMeta) -> str | None:
    """The state of the match just before a goal, in words: who was behind, level or ahead (the story the colour line reacts to)."""
    if m.kind != "goal_analysis" or "score" not in m.params:
        return None
    h, a = (int(x) for x in str(m.params["score"]).split("-"))
    home = meta.teams["H"].name
    side = "H" if m.params.get("team") == home else "A"
    h, a = (h - 1, a) if side == "H" else (h, a - 1)
    scorer = home if side == "H" else meta.teams["A"].name
    own, opp = (h, a) if side == "H" else (a, h)
    if own < opp:
        return f"{scorer} were behind"
    if own == opp:
        return "it was level" if own else "it was goalless"
    return f"{scorer} were already ahead"


def _swing(m: Moment) -> str | None:
    """How far a goal moved the game, in words (the win probability stays a graphic): for the side that scored."""
    before, after = m.params.get("win_before"), m.params.get("win_after")
    if before is None or after is None:
        return None
    d = after - before
    return "it turns the game" if d >= 0.35 else "a big swing" if d >= 0.2 else "a real lift" if d >= 0.1 else "a small change"


def facts_of(m: Moment, snapshot: dict, meta: MatchMeta) -> dict:
    """The facts block of an analyst moment, as the prompt shows it (the core and the world booth share it)."""
    p = render_params(m, "en")
    p.pop("tags", None)
    if "score" in p:  # the moment's own score is home-away too; name it so the model cannot read it as scorer-first
        p["score_home_away"] = p.pop("score")
    for key in (*SPOKEN_NEVER, *DERIVED):  # v5: no probability, xG or count reaches the prompt, so none can reach a spoken line
        p.pop(key, None)
    if "scorer_goals" in p:
        p["scorer_goals_today"] = p.pop("scorer_goals")
    if "chain" in p:
        p["chain"] = list(p["chain"])
    swing = _swing(m)
    if swing and m.kind != "goal_analysis":  # a goal's meaning is its idiom from the score and the tags, not a size of swing
        p["how_much_it_changes"] = swing
    before = _before_goal(m, meta)
    if before:
        p["before_this_goal"] = before
    match = {"home": meta.teams["H"].name, "away": meta.teams["A"].name,
             "score_home_away": f"{snapshot['score'][0]}-{snapshot['score'][1]}"}
    if m.params.get("squad"):
        match["squad"] = m.params["squad"]
    if m.kind == "pattern_insight":  # the habit as one block, as the system prompt names it ("short" is the club's first word, a template helper)
        p.pop("short", None)
        p = {"pattern": {k: v for k, v in p.items() if k in PATTERN_KEYS}, **{k: v for k, v in p.items() if k not in PATTERN_KEYS}}
    out = {"moment": {"kind": m.kind, "voice": m.voice, "match_clock": m.clock, **p, "tags": m.params.get("tags", "")}, "match": match}
    if snapshot.get("so_far"):  # v9, live runs: the match so far, so a booth that joined late knows the goals before it (runner._snap)
        out["match_so_far"] = snapshot["so_far"]
    return out


def build_prompt(m: Moment, snapshot: dict, meta: MatchMeta, only: list[str] | None = None,
                 feedback: dict[str, str] | None = None, recent: dict[str, list[str]] | None = None) -> str:
    """The user message for one moment. `recent` maps a channel key to the lines that channel spoke last (oldest first):
    the booth's own continuity, taken from lines already shown or spoken, never a source of facts."""
    facts = facts_of(m, snapshot, meta)
    keys = only or KEYS
    payoff = m.kind == "goal_analysis" and "pays_off" in m.params
    energy = energy_of(m)
    role = "co-commentator" if m.voice == "analyst" else "lead (play-by-play)"
    who = ", ".join(f"{k} {BOOTH[k].co.name if m.voice == 'analyst' else BOOTH[k].lead.name}" for k in keys)
    parts = [
        f"This moment is the {role}'s ({who}). Energy: {energy}. {(ENERGY_NOTE_ANALYST if m.voice == 'analyst' else ENERGY_NOTE)[energy]}",
        f"Angle: {ANGLE_PAYOFF if payoff else ANGLE.get(m.kind, 'One sharp thought about what just happened.')}",
        "", "Facts (the only source you may use; " + TAG_MEANING + "):", json.dumps(facts, ensure_ascii=False, indent=1),
        "", "Room per line (stay inside it, it is cut off on air otherwise):",
    ]
    for k in keys:
        sec, words, chars = room_of(m.kind, k, PAYOFF_EXTRA_S if payoff else 0.0)
        parts.append(f"- {k}: about {sec:g} s, at most {words} words, at most {chars} characters")
    said = {k: [t for t in (recent or {}).get(k, [])[-RECENT_LINES:] if t] for k in keys}
    if any(said.values()):
        parts += ["", "Continuity. The booth just said these lines on each channel, oldest first (on a goal, the last one is the lead's call). Do not repeat their wording or their meaning, do not open "
                  "like the last one, and do not copy a number from them (numbers come from the facts only). You may nod back to one of them:"]
        for k in keys:
            if said[k]:
                parts.append(f"{k}:")
                parts += [f'  - "{t}"' for t in said[k]]
    setup = {k: (recent or {}).get(f"{SETUP}{k}", [""])[-1] for k in keys}
    if any(setup.values()):
        if "pays_off" in m.params:
            parts += ["", "Earlier in this broadcast the co-commentator pointed out the habit in \"pays_off\", on each channel. This goal broke it: open with a short "
                      "callback to that line in a few words, then the picture of how it broke. No number:"]
        else:
            parts += ["", "Earlier in this broadcast the co-commentator said this about a habit. This goal did NOT come that way: do not refer back to it:"]
        parts += [f'- {k}: "{setup[k]}"' for k in keys if setup[k]]
    after = {k: (recent or {}).get(f"{AFTER}{k}", [""])[-1] for k in keys}
    if any(after.values()):
        parts += ["", "The lead's line right AFTER yours, on each channel. Do not say its idiom or the score before it:"]
        parts += [f'- {k}: "{after[k]}"' for k in keys if after[k]]
    parts += [
        "", "Write one line for each of these keys (language/style): " + ", ".join(keys) + ".",
        'Answer as JSON like {"en/beginner": "...", "en/expert": "..."} with exactly those keys.',
    ]
    if feedback:
        parts += ["", "Your previous lines were rejected by the fact checker. Fix exactly these problems:"]
        parts += [f"- {k}: {v}" for k, v in feedback.items()]
    return "\n".join(parts)


def parse_lines(raw: str, wanted: list[str]) -> dict[str, str]:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in answer")
    data = json.loads(raw[start:end + 1])
    return {k: str(data[k]).strip() for k in wanted if k in data and str(data[k]).strip()}


class GuardedLLM:
    """Wraps a model call with a disk cache and a hard call budget.

    A call that is under way is shared: a second request for the same prompt (a live stream that restarted, for
    example) waits for it instead of paying again, and it finishes and is cached even if its first caller went away."""

    def __init__(self, call: LLM, budget: CallBudget, model: str, cache_dir: Path | None = None,
                 use_cache: bool = True, inflight: dict[str, asyncio.Task] | None = None, version: str = PROMPT_VERSION):
        """`use_cache=False` is fresh mode: the disk cache is neither read nor written, every prompt is a real call.
        `inflight` is shared between the wrappers of one server, so calls under way are visible to all of them."""
        self._call, self.budget, self.model, self.use_cache = call, budget, model, use_cache
        self.version = version  # the prompt version in the cache key: each system prompt (core, world booth) has its own
        self.inflight = inflight if inflight is not None else {}
        self.cache_dir = cache_dir if cache_dir is not None else ROOT / "data" / "cache" / "analyst"
        if use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.last_latency_s = 0.0
        self.last_cached = False

    def _path(self, prompt: str) -> Path:
        h = hashlib.sha256(f"{self.version}|{self.model}|{prompt}".encode()).hexdigest()[:24]
        return self.cache_dir / f"{h}.json"

    def has(self, prompt: str) -> bool:
        """True when this prompt would be answered from the disk cache, without a model call."""
        return self.use_cache and self._path(prompt).exists()

    def discard(self, prompt: str) -> None:
        """Forget a cached answer that turned out to be unusable."""
        self._path(prompt).unlink(missing_ok=True)

    async def __call__(self, prompt: str) -> str:
        path = self._path(prompt)
        if self.use_cache and path.exists():
            hit = json.loads(path.read_text(encoding="utf-8"))
            self.last_cached, self.last_latency_s = True, hit["latency_s"]
            return hit["text"]
        task = self.inflight.get(path.name)
        if task is None:
            self.budget.take()
            task = self.inflight[path.name] = asyncio.ensure_future(self._fetch(prompt, path))
            task.add_done_callback(lambda t, name=path.name: self._settled(name, t))
        text, self.last_latency_s = await asyncio.shield(task)  # a cancelled caller does not cancel the call
        self.last_cached = False
        return text

    async def _fetch(self, prompt: str, path: Path) -> tuple[str, float]:
        t0 = time.perf_counter()
        text = await self._call(prompt)
        if not (text or "").strip():  # an empty answer is never cached or published: one retry, paid from the same budget
            self.budget.take()
            text = await self._call(prompt)
            if not (text or "").strip():
                raise EmptyAnswer("the model returned no text twice")
        latency = time.perf_counter() - t0
        if self.use_cache:
            path.write_text(json.dumps({"text": text, "latency_s": round(latency, 2), "model": self.model},
                                       ensure_ascii=False), encoding="utf-8")
        return text, latency

    def _settled(self, name: str, task: asyncio.Task) -> None:
        self.inflight.pop(name, None)
        if not task.cancelled():
            task.exception()  # mark as retrieved: a call nobody waits for any more may fail quietly


# Live commentary needs the line in seconds. Haiku 5.5 thinks by default (adaptive, effort medium) and thinking counts toward
# max_tokens: with max_tokens 16000 one answer took 3,947 output tokens and 16.4 s. Thinking off is allowed on Haiku 5.5 at
# effort high or below (the default medium); six short lines of JSON fit easily in 2048 tokens.
ANALYST_OPTIONS = {"max_tokens": 2048, "thinking": {"type": "disabled"}}


def claude_llm(model: str, api_key: str, instructions: str | None = None, name: str = "Analyst") -> LLM:
    """The analyst as a Microsoft Agent Framework agent backed by Claude (`instructions`: another system prompt, the world booth's)."""
    from agent_framework.anthropic import AnthropicClient

    agent = AnthropicClient(model=model, api_key=api_key).as_agent(
        name=name, instructions=SYSTEM if instructions is None else instructions, default_options=ANALYST_OPTIONS)

    async def call(prompt: str) -> str:
        return (await agent.run(prompt)).text

    return call
