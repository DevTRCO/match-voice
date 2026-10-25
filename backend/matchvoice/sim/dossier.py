"""The dossier: the background a commentator brings to a match, invented like everything else and fixed by the seed.

A real commentator fills a quiet spell with what they know before kick-off: the form, the table, the coach, the last
meeting, a player's old club or a milestone. The simulator has none of that, so this module makes it up, deterministically
from the match (the same match always has the same dossier) and consistent with it (the arc's story, the squads, the season
numbers already in the meta). Every story is a small set of facts with numbers and names, so the verifier can check a line
built on it, and every story is used at most once in a match.

    dossier_of(meta) -> Dossier
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..schema import MatchMeta, Player
from .names import CLUB_PREFIX, CLUB_SUFFIX, GIVEN, SURNAME

SEASON_GAMES = 11  # league games played before this one


@dataclass(frozen=True)
class Story:
    id: str  # unique within the match, e.g. "H:form" or "H7:former_club"
    kind: str  # form | table | coach | comebacks | last_meeting | home_run | former_club | milestone | academy
    side: str  # "H" or "A"
    player: str | None  # player id for a player story
    data: dict  # the facts: numbers and names a line may use, and nothing else
    weight: float  # how good a story it is: the topic picks the best fitting one first


@dataclass
class Dossier:
    stories: list[Story] = field(default_factory=list)

    def for_side(self, side: str) -> list[Story]:
        return [s for s in self.stories if s.side == side and s.player is None]

    def for_player(self, pid: str) -> list[Story]:
        return [s for s in self.stories if s.player == pid]


def _surname(name: str) -> str:
    return name.split()[-1]


def _form(rng: random.Random, strong: bool) -> str:
    p = (0.5, 0.25) if strong else (0.3, 0.3)
    return "".join("W" if (r := rng.random()) < p[0] else "D" if r < p[0] + p[1] else "L" for _ in range(5))


def dossier_of(meta: MatchMeta) -> Dossier:
    rng = random.Random(f"dossier:{meta.id}")
    taken = {t.name for t in meta.teams.values()}
    others = [f"{p} {s}" for p in CLUB_PREFIX for s in CLUB_SUFFIX if f"{p} {s}" not in taken and not any(p in n for n in taken)]
    rng.shuffle(others)
    stories: list[Story] = []
    roster = {_surname(p.name) for t in meta.teams.values() for p in t.players}
    home, away = meta.teams["H"], meta.teams["A"]

    # the table: two different places, the one with more points higher up
    places = rng.sample(range(2, 19), 2)
    for side, place in zip(("H", "A"), sorted(places) if rng.random() < 0.5 else sorted(places, reverse=True)):
        points = max(4, round((20 - place) * 1.55 + rng.randint(-2, 2)))
        stories.append(Story(f"{side}:table", "table", side, None, {"team": meta.teams[side].name, "place": place, "points": points,
                                                                       "games": SEASON_GAMES}, 0.5))
        form = _form(rng, place <= 8)
        wins = form.count("W")
        losses = form.count("L")
        stories.append(Story(f"{side}:form", "form", side, None, {"team": meta.teams[side].name, "wins": wins, "draws": form.count("D"),
                                                                     "losses": losses, "of": 5, "form": form}, 0.7))
        coach = f"{rng.choice(GIVEN)} {rng.choice([s for s in SURNAME if s not in roster])}"  # never a surname of either squad
        stories.append(Story(f"{side}:coach", "coach", side, None, {"team": meta.teams[side].name, "coach": coach,
                                                                       "coach_surname": _surname(coach), "years": rng.randint(1, 6)}, 0.55))
        comebacks = rng.randint(1, 3) if meta.arc == "comeback" and side == "H" else rng.randint(0, 1)
        if comebacks:
            stories.append(Story(f"{side}:comebacks", "comebacks", side, None, {"team": meta.teams[side].name, "n": comebacks,
                                                                                   "games": SEASON_GAMES}, 0.95 if meta.arc == "comeback" else 0.6))
    run = rng.randint(3, 7)
    stories.append(Story("H:home_run", "home_run", "H", None, {"team": home.name, "n": run, "venue": meta.venue}, 0.6))

    # the last meeting, with a scorer from today's squads when there was a goal
    hg, ag = rng.choice([(1, 0), (2, 1), (0, 0), (1, 1), (0, 2), (3, 1), (2, 2)])
    scorers = [p for p in (home if hg >= ag else away).players if p.group in ("FWD", "MID")]
    last = {"home": home.name, "away": away.name, "hg": hg, "ag": ag}
    if hg + ag and scorers:
        p = rng.choice(scorers)
        last |= {"scorer": _surname(p.name), "scorer_id": p.id, "scorer_team": (home if hg >= ag else away).name}
    stories.append(Story("H:last_meeting", "last_meeting", "H", None, last, 0.85))

    # players: an old club, a milestone, an academy graduate
    for side, team in (("H", home), ("A", away)):
        for p in team.players:
            stories += _player_stories(rng, side, team.name, p, others)
    return Dossier(stories)


def _player_stories(rng: random.Random, side: str, team: str, p: Player, clubs: list[str]) -> list[Story]:
    out: list[Story] = []
    name = _surname(p.name)
    age = p.age or 26
    apps_now = (p.season.apps if p.season else 8) + 1  # this match counts
    if age <= 21 and rng.random() < 0.7:
        out.append(Story(f"{p.id}:academy", "academy", side, p.id, {"player": name, "team": team, "age": age}, 0.65))
    elif rng.random() < 0.6:
        years = rng.randint(1, min(5, max(1, age - 20)))
        out.append(Story(f"{p.id}:former_club", "former_club", side, p.id, {"player": name, "team": team, "club": rng.choice(clubs),
                                                                              "years": years}, 0.6))
    if age >= 27 and rng.random() < 0.35:
        n = rng.choice([50, 60, 70, 75, 80, 90])  # said in words, which go to 99
        out.append(Story(f"{p.id}:milestone", "milestone", side, p.id, {"player": name, "team": team, "n": n}, 0.8))
    elif apps_now == 1 and rng.random() < 0.8:
        out.append(Story(f"{p.id}:debut", "debut", side, p.id, {"player": name, "team": team}, 0.75))
    return out
