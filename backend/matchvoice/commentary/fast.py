"""The fast and the context layer (docs/DATA-MODEL.md 7.1 and 7.2): a constant, cheap voice under the analyst. No model call.

`build_layers(meta, events, rows)` turns the skeleton, the enriched rows (`sim/micro/enrich.py`) and the tactics plan into moments:

    fast     the caller's fragments, names and verbs: who plays it (pass_kind), who takes it (touch); each name once per hop, and carry, duel, restart,
             setpiece_setup, press_on, plus the kinds that wait for tracking: take_on, in_behind, line_break, block, duel_1v1
    context  the colour analyst's template lines (player_note, counter_note, fatigue_note, tempo_note, shape_note, press_note,
             phase_note), offered in slots: a dead ball, or a receiver who still holds the ball 1.5 s after the receipt

Time of knowledge (0.1): a moment is stamped with the time a viewer could know what it says. A kick row is known at the kick, a
receipt at its arrival, a carry at its end. The builder walks one timeline in time order and a moment reads only what happened
before it: a context slot is offered only if nothing happened between its creation and its time (`test_fast.py` cuts the data and
compares). A receipt is called only once the receiver has kept the ball for a moment (`TOUCH_SETTLE_S`). Names are rationed in the builder:
a name-less fragment exists only for a ball worth a word (a chested ball, a switch, a clearance, a carry) and never two in a row while one
team keeps the ball (`NAMED_EVERY`). A name is not said again within `NAME_GAP_S`: a routine kick whose kicker was just named (his receipt, a tackle, a duel) is not
called (or, when it shows something, called without him), a typed pass names only its target, a carry goes name-less. Context lines are built at the pace the director voices them (`CONTEXT_DEAD_S`, `CONTEXT_PLAY_S`, three
to a dead-ball window), so a built line is not dropped by the voice and the fact it used is not lost. Caps, replacement and the pace of the
voice live in the director (`ChannelDirector(dense=True)`).
"""
from __future__ import annotations

import bisect
from collections import deque
from dataclasses import dataclass

from ..facts.engine import FactEngine
from ..schema import PITCH_L, PITCH_W, Event, EventType, MatchMeta, Player, Side
from ..sim.dossier import dossier_of
from ..sim.tactics import plan_at
from .director import CONTEXT_DEAD_S, CONTEXT_PER_WINDOW, CONTEXT_PLAY_S
from .moments import Moment, MomentBuilder, surname

FAST_BASE = 1_000_000
TACTICAL_BASE = 2_000_000  # the analyst's tactical_shift moments (phase 7)
CONTEXT_BASE = 3_000_000
REPLACED_KINDS = ("long_ball", "pass_final_third")  # skeleton calls the fast layer takes over (7.1): built, not pushed

CONTEXT_FIRST_HOLD_S = 1.5  # a receiver who still holds the ball this long after the receipt opens a slot
SLOT_SLACK_S = 1.0  # a context line may start up to 3 s after its slot (the voice wait) and the director then spaces the next one from that start: build with this much room
DEAD_STEP_S = CONTEXT_DEAD_S + SLOT_SLACK_S  # dead-ball slots are this far apart, as far apart as the director voices two lines of a dead ball
DEAD_SLOTS = 6  # slots offered after a stoppage, from 1 s on; at most CONTEXT_PER_WINDOW of them become a line (the director's cap), the rest find nothing to say
PRESS_HIGH_X = 60.0  # a press is "high" when the presser stands this far up the pitch in his own attacking direction (opponent's half, metres)
FREE_KICK_RANGE_M = 32.0
MAX_FLIGHT_TTL_S = 4.0  # a pass fragment lives at most this long (viewer seconds)
CARRY_MIN_PROGRESS_M = 6.0
SECOND_HOLD_S = 4.5  # a receiver who still holds the ball this long after the receipt opens a second slot
RESTART_TYPES = ("throw_in", "goal_kick", "kickoff")
TOUCH_DIR_M = 8.0
THIRD_X = (PITCH_L / 3, 2 * PITCH_L / 3)  # thirds of the pitch in the attacking frame: own, middle, final
QUIET_SLOTS_S = (4.0, 10.0, 16.0)  # nothing has happened for this long and the ball is not dead (a saved shot, a ball in the air for a restart): room for a context line
SIDES = ("left", "centre", "right")
GOAL_QUIET_S = 17.0  # after a goal the voice has the call, the co-commentator's line and the lead's score line to get through, with a breath before each of the last two (director.BREATH_S): the first context slot comes after all three
ROUTINE_PASS = ("short",)  # a routine pass is the kicker ("X plays it on.") and then the receiver ("Inside to Y."), each name once, with what the kick shows when it shows something, never mechanics (COMMENTATOR.md: ball movement is 2.7% of what a commentator says)
SPELL_S = 240.0  # first touch after a spell longer than this
CORNER_WINDOW_S = 300.0
SCENE_TOUCH_GAP_S = 0.3  # a generated live scene: a receipt is not called when the next action (the shot) comes within this long of the call
SCENE_FINAL_TYPES = ("cross", "cut_back", "through")  # a generated live scene: the ball that makes the chance is called ahead of a touch or a press
SCENE_FINAL_PRIO = 38
SCENE_FINAL_WAIT_S = 1.5  # and it waits for the line on air to end
SCENE_CARRY_GAP_S = 8.0  # a generated live scene's attack: at most one carry line in this long
SCENE_SETTLE_S = 0.8  # a generated live scene: a receipt is called once the receiver has kept the ball this long
SCENE_HEAD_SETTLE_S = 1.2  # a generated live scene: a header is called once nothing followed it for this long (a headed finish comes sooner)
TOUCH_SETTLE_S = 0.5  # a receipt is called once the receiver has kept the ball this long: a first-time pass, a carry or a shot sooner voids it (the next fragment is that action)
NAME_GAP_S = 6.0  # a player named by a fragment is not named again by the next one within this long: his own routine kick after the receipt that named him is not called
PLAY_NOTE_GAP_S = 120.0  # one-fact player notes while the ball is in play at most this often (match seconds)
SHOWN_GAP_S = 8.0  # a routine kick whose kicker was just named is called, without his name, only when it shows something (closed down, hit hard and low) and at most this often
PLACE_EVERY_S = 150.0  # a pitch zone ("in the final third") is said at most this often, and never the zone just said
BARE_PASS = ("switch", "cross", "clearance")  # the pass types a caster may leave unnamed ("Switched from the right."); the others always name their target
TEMPO_WINDOW_S = 180.0
TEMPO_SLOW_PPM, TEMPO_SLOW_EXIT_PPM = 3.5, 4.5  # completed passes per minute of one team over the last three minutes: enter "slow" below the first, leave it above the second
TEMPO_HIGH_PPM, TEMPO_HIGH_EXIT_PPM = 9.0, 8.0  # enter "high" above the first, leave it below the second
TEMPO_HAS_BALL = 0.55  # a tempo claim is about the side that has the ball: at least this share of both sides' completed passes in the window
NAMED_EVERY = 2  # while one team keeps the ball, at most one name-less fragment in a row, and only for a ball worth a word (the profile has 38% of segments naming a player; the skeleton, the counters and the analyst fill the rest)
PASSES_STEP = 12  # a player's pass count is news again after this many more completed passes
PASSES_MIN, PASSES_MAX = 12, 99  # number words stop at 99 (delivery.number_words)
PLAYER_GAP_S = 300.0  # the same player gets a note at most this often (match seconds); a fact about a player is said once per match (7.2)
STAT_GAP_S = 120.0  # the same match fact for the same team at most this often
STAT_FACETS = ("shots_total", "corners_total", "fouls_total", "possession", "crosses_total", "long_total", "won_back_total", "on_target_total", "saves_total",
               "throws_total", "goal_kicks_total", "recent_ball", "drought")
STAT_FLOOR = {"possession": 58, "recent_ball": 62, "long_total": 6, "won_back_total": 6, "throws_total": 5, "goal_kicks_total": 5, "drought": 10}  # a fact is worth saying from this value on (default 3)
STAT_STEP = {"possession": 5, "recent_ball": 8, "drought": 5, "throws_total": 3, "goal_kicks_total": 3}  # and again when it has moved this far (default 1)
RECENT_MIN_PASSES = 10  # the last three minutes say something about the ball from this many completed passes of both sides
STAT_MAX = 3  # and at most this many times per match for one team and fact (the value must have grown each time)
STAT_MAX_BY = {"drought": 1, "throws_total": 1, "goal_kicks_total": 1, "long_total": 2, "fouls_total": 2}  # the facts the review read as a ticker (only their number moved) have fewer lines
MINOR_NEWS = ("passes", "passes_2", "spell", "spell_end", "corners", "fouls", "shots")  # counter news that is a figure, not a goal's move or tally
MINOR_GAP_S = 90.0  # a stat or a minor news line at most this often, whichever side and fact: no three figures in a row, and the dead ball has room for the colour
NEWS_MAX = {"spell_end": 3, "fouls": 3, "corners": 4}  # lines of one minor news kind in a match
SPELL_MIN_PASSES = 5  # a move of this many passes without a turnover is recapped when it ends in a stoppage
STREAK_MAX = 4  # pass-streak notes in a whole match (each team: ten, then fifteen, then twenty, never the same number twice)
STATE_STEP_S = 300.0  # the score and the clock come back after five match minutes, or when the score has changed ...
STATE_GAP_S = 60.0  # ... but never within a minute of the last time
STATE_FROM_MIN = 10  # and not before the tenth minute unless a goal has changed the score
NEWS_TTL_S = 30.0  # counter news waits this long for a slot
NEWS_RANK = {"move": 0, "tally": 1, "tally_first": 1}  # after a goal its move comes first, then the tally; the rest in order of time
FATIGUE_MIN_T = 60 * 60.0
FATIGUE_AT = 0.7
SEASONAL = ("season", "assists", "clean_sheets", "apps")  # the facets whose clause ends on "this season"
NOTABLE_ROLES = ("poacher", "target_forward", "playmaker", "ball_playing_cb", "sweeper_keeper", "inverted_winger", "box_to_box", "anchor")
HOLD_COOLDOWN_S = {"phase_note": 480.0, "press_note": 900.0, "tempo_note": 180.0, "shape_note": 120.0}
TACTIC_KINDS = ("shape_note", "press_note", "phase_note")  # three ways to say how a side sets up: one of them per side at a time, or the same thing is said three times in half a minute
TACTIC_GAP_S = 90.0
TACTIC_IDEA = {"protect": "deep", "passive": "deep", "low": "deep", "ten_men": "ten_men", "chase": "chase", "intense": "high", "high": "high",
               "counter": "counter"}  # the shape, the press and the phase of a side say one idea in three ways ("dropped deep", "happy to let the ball go", "sit in a low block"): an idea is said once per side in a match
TEMPO_MAX = 2  # tempo notes per side in a match: the first and the second wording, then the fact has been said
STAT_TWINS = {"on_target_total": ("on_target_total", "saves_total"), "saves_total": ("on_target_total", "saves_total")}  # facets that say the same numbers
ZEROABLE = ("m", "sh", "so")  # the other side's count in a sentence "and X have had N of their own": a zero is no contrast and the short sentence stands
WORK_RATE_W = {"low": 0.9, "medium": 1.0, "high": 1.15}


@dataclass(frozen=True)
class Spec:
    priority: int
    ttl: float  # viewer seconds
    wait: float  # viewer seconds the voice may take to start it
    slot: int  # 0..7, the low bits of the derived id (kinds that cannot meet on one eid may share)


FAST: dict[str, Spec] = {  # table 7.1; priority 26 to 40, above min_priority (25), never interrupting
    "touch": Spec(26, 3.0, 2.2, 0),
    "pass_kind": Spec(27, 2.0, 1.0, 1),  # the kicker of a routine pass is the bottom of the pile: it must not push a foul or a tackle call out of the voice
    "restart": Spec(28, 3.0, 1.5, 1),
    "setpiece_setup": Spec(40, 4.0, 2.0, 1),
    "carry": Spec(30, 2.0, 1.0, 2),
    "take_on": Spec(34, 2.0, 1.0, 3),
    "duel_1v1": Spec(34, 2.0, 1.0, 3),
    "duel": Spec(34, 2.0, 1.0, 4),
    "block": Spec(36, 2.5, 1.0, 4),
    "press_on": Spec(30, 1.5, 0.8, 5),
    "in_behind": Spec(38, 2.5, 1.0, 6),
    "line_break": Spec(36, 2.0, 1.0, 7),
}
CONTEXT: dict[str, Spec] = {  # priority 30 to 45, ttl 8 s, voice wait 3 s
    "tempo_note": Spec(32, 8.0, 3.0, 0),
    "press_note": Spec(34, 8.0, 3.0, 1),
    "phase_note": Spec(34, 8.0, 3.0, 2),
    "shape_note": Spec(36, 8.0, 3.0, 3),
    "fatigue_note": Spec(38, 8.0, 3.0, 4),
    "counter_note": Spec(40, 8.0, 3.0, 5),
    "player_note": Spec(42, 8.0, 3.0, 6),
    "story_note": Spec(44, 8.0, 3.0, 7),  # the dossier: what the booth knows before kick-off, for a quiet spell
}
RATIONED = ("touch", "pass_kind", "carry", "duel")
LEAD_CONTEXT = ("story_note",)  # context kinds the lead says: in a quiet spell the caller reads the club's record off his notes (docs/INSERT-SCRIPT.md)
STORY_GAP_S = 150.0  # one dossier story per this many match seconds at most
STORY_ROOM = (600.0, 13)  # and only while the context layer has said fewer than 13 lines in the last 10 minutes: a story takes room, it does not add a ticker line
STORY_FROM_S = 120.0
COMEBACK_STORY_T = 64 * 60.0  # "they have come from behind before" waits for the last half hour, when it can still matter  # kinds with name-less wordings


def story_params(st) -> dict:
    """The template facts of a dossier story: its facet (the wording) and its numbers and names under the keys the renderer knows."""
    d = st.data
    k = st.kind
    p: dict = {"story": st.id}
    if k == "table":
        p |= {"facet": "table", "place": d["place"], "n": d["points"]}
    elif k == "form":
        p |= {"facet": "form_winless" if not d["wins"] else "form_one" if d["wins"] == 1 else "form", "n": d["wins"], "m": d["losses"]}
    elif k == "coach":
        p |= {"facet": "coach_new" if d["years"] == 1 else "coach", "coach": d["coach"], "n": d["years"]}
    elif k == "comebacks":
        p |= {"facet": "comebacks" if d["n"] > 1 else "comebacks_once", "n": d["n"]}
    elif k == "home_run":
        p |= {"facet": "home_run", "n": d["n"], "venue": d["venue"]}
    elif k == "last_meeting":
        p |= {"facet": "last_meeting" if d.get("scorer") else "last_meeting_0", "goals_h": d["hg"], "goals_a": d["ag"]}
        if d.get("scorer"):
            p["player"] = d["scorer"]
    elif k == "former_club":
        p |= {"facet": "former_club" if d["years"] > 1 else "former_club_1", "player": d["player"], "club": d["club"], "n": d["years"]}
    elif k == "milestone":
        p |= {"facet": "milestone", "player": d["player"], "count": d["n"]}
    elif k == "academy":
        p |= {"facet": "academy", "player": d["player"], "n": d["age"]}
    elif k == "debut":
        p |= {"facet": "debut", "player": d["player"]}
    return p


def layer_of(moment_id: int) -> str:
    """skeleton | fast | context, from the derived id (0.2). tactical_shift ids (2,000,000 up) are analyst moments: skeleton here."""
    return "fast" if FAST_BASE <= moment_id < TACTICAL_BASE else "context" if moment_id >= CONTEXT_BASE else "skeleton"


def continuity_id(moment_id: int) -> bool:
    """The analyst's continuity holds only skeleton and analyst captions (7.3): ids under 1,000,000 and tactical_shift."""
    return moment_id < FAST_BASE or TACTICAL_BASE <= moment_id < CONTEXT_BASE


def _family(facet: str) -> str:
    """A player-note facet without the number that moves on: two notes of one family do not follow each other."""
    return "passes" if facet.startswith("passes:") else facet


def _dir(side: str, period: int) -> int:
    return 1 if (side == "H") == (period == 1) else -1


def _att(side: str, period: int, x: float, y: float) -> tuple[float, float]:
    return (x, y) if _dir(side, period) > 0 else (PITCH_L - x, PITCH_W - y)


def fatigue_base(p: Player, t: float) -> float:
    """5.10: a function of the clock and the profile only (starters play from 0)."""
    w = WORK_RATE_W[p.work_rate or "medium"]
    return max(0.0, min(1.0, (t / 60 / 90) * (1.25 - p.attrs.stamina / 100) * w))


def state_at(shifts, t: float) -> tuple[str, bool]:
    """(posture, ten_men) in force at `t`: the latest trigger among the shifts already in effect (as `plan_at`)."""
    posture, ten = "base", False
    for s in sorted(shifts or [], key=lambda s: s.t_trigger):
        if s.t <= t:
            posture, ten = s.posture, s.ten_men
    return posture, ten


@dataclass
class _Slot:
    t: float  # when the line may speak
    dead: bool
    window: int  # eid of the stoppage (dead) or of the receipt (hold)
    holder: str | None  # player on the ball
    team: str
    long: bool = False  # the ball has been held a long time: there is room for the long wording
    exclude: str | None = None  # a side whose players get no player note in this slot (the side that has just conceded)


@dataclass(order=True)
class _Rec:
    t: float
    order: int
    kind: str = ""  # ev | row
    payload: object = None


class Layers:
    """One pass over a match. Use `build_layers`."""

    def __init__(self, meta: MatchMeta, events: list[Event], rows: list[dict], scene_at: float | None = None):
        self.meta, self.events, self.rows = meta, events, rows
        # a generated live scene (sim/scene.py) from this match second on: a carry is play from its first stride, and from a ball won back in
        # play until the next stoppage the booth calls the attack only (no story, table or stats line in the winning move)
        self.scene_at = scene_at
        self.attack_on = False
        self.carry_said = -1e9  # time of the last carry line
        self.players: dict[str, Player] = {p.id: p for t in meta.teams.values() for p in t.players}
        self.names = {pid: surname(p.name) for pid, p in self.players.items()}
        full = {s: meta.teams[s].name for s in ("H", "A")}
        first = {s: n.split()[0] for s, n in full.items()}
        # a club is named by its first word, as a broadcaster would, unless both clubs start alike
        self.team_name = first if first["H"] != first["A"] else full
        self.ev_t = [e.t for e in events]
        self.taken = self._skeleton_events()
        self.ev_by_i = {e.i: e for e in events}
        self.out: list[Moment] = []
        self.used: set[int] = set()
        # rationing and context state
        self.last_fast: tuple[str, bool] | None = None
        self.bare_run = 0  # name-less fragments in a row
        self.pending: list[_Slot] = []
        self.team_of: dict[str, str] = {pid: s for s in ("H", "A") for pid in (p.id for p in meta.teams[s].players)}
        self.holder: str | None = None
        self.holder_team: Side | None = None
        self.corners: dict[str, deque[float]] = {"H": deque(), "A": deque()}
        self.fouls: dict[str, int] = {}
        self.shots = {"H": 0, "A": 0}
        self.goals = {"H": 0, "A": 0}
        self.state_at = -1e9  # time of the last game-state line
        self.state_score = (0, 0)  # the score it spoke of
        self.state_turn = 0
        self.streak: dict[str, int] = {"H": 0, "A": 0}
        self.streak_best: dict[str, int] = {"H": 0, "A": 0}  # the longest streak of each side that became news: a streak is news again only when it is longer
        self.streak_lines = 0
        self.streak_told: dict[str, int] = {"H": 0, "A": 0}  # the length of the running move that was already said as news ("kept the ball for ten passes now"): its end is not said again
        self.play_note_at = -1e9  # time of the last one-fact player note while the ball was in play
        self.shown_at = -1e9  # time of the last name-less routine kick (closed down, hit hard and low)
        self.named_at: dict[str, float] = {}  # surname -> time a fast fragment last named him
        self.minor_at = -1e9  # time of the last stat or minor news line built
        self.news_n: dict[str, int] = {}  # minor news kind -> lines built
        self.idea_said: set[tuple[str, str]] = set()  # (side, idea) of the tactical notes built
        self.completed: dict[str, deque[float]] = {"H": deque(), "A": deque()}
        self.last_touch: dict[str, float] = {}
        self.news: list[dict] = []  # counter news waiting for a slot
        self.news_said: set[tuple] = set()  # (facet, team, player, number) of the news already used: a news line is said once in a match
        self.ctx_last = -1e9  # time of the last context line built
        self.ctx_window: dict[int, int] = {}  # dead-ball window -> context lines built in it
        self.touch_due: tuple | None = None  # the receipt waiting out TOUCH_SETTLE_S
        self.kicked: set[int] = set()  # eids of the passes whose kick fragment named the target: their receipt adds nothing unless it is worth a word, and then it does not name the target and the kicker again
        self.split_kicks: set[int] = set()  # eids of the routine passes: the kick (when it is called) has the kicker or nobody, the receipt names the receiver and never the kicker
        self.place_at = -1e9  # time and zone of the last pitch-zone readout
        self.place_last: tuple[str, str] | None = None
        self.note_at: dict[str, float] = {}  # player -> time of his last player_note
        self.dossier = dossier_of(meta)
        self.story_said: set[str] = set()  # ids of the dossier stories told: each once a match
        self.story_at = -1e9  # time of the last story
        self.ctx_times: list[float] = []  # times of the context lines built
        self.said_facets: dict[str, dict[str, float]] = {}  # player -> facet -> time it was said
        self.last_facet: str | None = None  # the facet of the last player note: the next one is another
        self.chain: list[str] = []  # the players of the move in progress, in the order they touched the ball
        self.chain_team: str | None = None
        self.match_goals: dict[str, int] = {}  # player -> goals scored in this match so far (the season numbers are from before it)
        self.match_assists: dict[str, int] = {}
        self.passes_done: dict[str, int] = {}  # player -> passes of his that have arrived (known at the receipt)
        self.pass_actor: dict[int, str] = {}  # eid of a pass -> the player who kicked it
        self.pass_n = {"H": 0, "A": 0}
        self.corner_n = {"H": 0, "A": 0}
        self.foul_n = {"H": 0, "A": 0}
        self.cross_n = {"H": 0, "A": 0}
        self.long_n = {"H": 0, "A": 0}  # long balls
        self.won_n = {"H": 0, "A": 0}  # balls won back: a tackle or an interception
        self.on_target_n = {"H": 0, "A": 0}  # shots on target (saved or scored)
        self.saves_n = {"H": 0, "A": 0}  # saves made BY the side's keeper
        self.throw_n = {"H": 0, "A": 0}
        self.gk_n = {"H": 0, "A": 0}
        self.last_shot_t = {"H": 0.0, "A": 0.0}  # a side that has not shot yet has been without one since kick-off
        self.shot_t: dict[str, list[float]] = {"H": [], "A": []}
        self.stat_said: dict[tuple[str, str], tuple[float, int]] = {}  # (facet, team) -> (time, value) of the last stats line
        self.stat_count: dict[tuple[str, str], int] = {}  # (facet, team) -> stats lines of it so far
        self.stat_turn = 0
        self.tallest = max((p for p in self.players.values() if p.group != "GK"), key=lambda p: (p.height_cm or 0, p.id), default=None)
        self.fatigue_said: set[str] = set()
        self.tempo_class: dict[str, str] = {"H": "measured", "A": "measured"}
        self.tempo_at: dict[str, float] = {"H": -1e9, "A": -1e9}
        self.shape_seen: dict[str, tuple[str, bool]] = {"H": ("base", False), "A": ("base", False)}
        self.press_seen: dict[str, str] = {}
        self.cool: dict[tuple[str, str], float] = {}
        self.tactic_at: dict[str, float] = {"H": -1e9, "A": -1e9}  # side -> time of its last shape, press or phase note
        self.tempo_n: dict[str, int] = {"H": 0, "A": 0}  # tempo notes said per side
        self.last_topic: str | None = None
        self.geom: dict[int, tuple[float, float, float, float, int, str]] = {}  # eid of a pass -> start, end, period, team

    # ---------- setup ----------
    def _skeleton_events(self) -> set[int]:
        """Events that already have a skeleton moment: the fast layer says nothing there (no double call, 7.1)."""
        eng = FactEngine(self.meta)
        mb = MomentBuilder(eng)
        taken: set[int] = set()
        for ev in self.events:
            for m in mb.feed(ev, eng.ingest(ev)):
                if m.kind not in REPLACED_KINDS:
                    taken.add(ev.i)
        return taken

    def clock_at(self, t: float) -> str:
        k = max(0, bisect.bisect_right(self.ev_t, t) - 1)
        return self.events[k].clock

    def minute_at(self, t: float) -> int:
        return int(self.clock_at(t).split("+")[0])

    # ---------- timeline ----------
    def timeline(self) -> list[_Rec]:
        recs: list[_Rec] = []
        annotated = {r["i"] for r in self.rows if r["k"] == 0}
        for e in self.events:
            if e.i not in annotated:
                recs.append(_Rec(round(e.t, 3), 16 * e.i, "ev", e))
        for r in self.rows:
            t = r["t"] + (r["duration_s"] if r["type"] == "carry" and "duration_s" in r else 0.0)  # a carry is known at its end
            recs.append(_Rec(round(t, 3), r["eid"], "row", r))  # milliseconds, as the moments carry them: one order for both
            if r["type"] == "carry" and self.scene_at is not None and r["t"] >= self.scene_at:  # a scene: the run is visible from its first stride
                recs.append(_Rec(round(r["t"], 3), r["eid"], "stride", r))
        recs.sort()
        return recs

    def run(self) -> list[Moment]:
        for rec in self.timeline():
            if rec.kind == "ev" and rec.payload.type is EventType.PRESSURE:  # a presser closing in does not move the ball
                self.settle(rec.t, keep=True)
                self.flush(rec.t, keep=True)
                self.on_pressure(rec.payload)
                continue
            if rec.kind == "stride":  # a carry under way is play: a quiet-spell slot after it is void (the carry itself is called at its end)
                self.flush(rec.t)
                continue
            self.settle(rec.t)
            self.flush(rec.t)  # whatever is left was due at or after this record, so something happened first: void
            if rec.kind == "ev":
                self.on_event(rec.payload)
            else:
                self.on_row(rec.payload, rec.t)
            self.quiet(rec.t, rec.order)
        self.settle(float("inf"))
        self.flush(float("inf"))
        self.out.sort(key=lambda m: (m.t, m.id))
        return self.out

    def quiet(self, t: float, window: int) -> None:
        """Whatever the record was, if nothing follows within a few seconds there is room for a line: a slot at 4, 10 and 16 s (each is void
        if anything happens first, see `flush`). A receipt keeps its own two hold slots and adds the later two."""
        if self.holder is None or self.holder_team is None:
            return
        if self.pending:
            if len(self.pending) == 2 and not self.pending[0].dead:  # the hold slots of a receipt
                self.pending += [_Slot(t + off, False, self.pending[0].window, self.holder, self.holder_team, long=True) for off in QUIET_SLOTS_S[1:]]
            return
        self.pending = [_Slot(t + off, False, window, self.holder, self.holder_team, long=off > 5.0) for off in QUIET_SLOTS_S]

    # ---------- emit ----------
    def _emit(self, specs: dict[str, Spec], base: int, kind: str, t: float, key: int, params: dict, ev_i: int, layer: str,
              flight: float = 0.0, prio: int | None = None, wait: float = 0.0) -> Moment | None:
        spec = specs[kind]
        mid = base + 8 * key + spec.slot
        if mid in self.used:
            return None
        self.used.add(mid)
        lead = layer == "fast" or kind in LEAD_CONTEXT  # the lead calls the play and reads the dossier; the co-commentator has the rest of the context
        m = Moment(id=mid, t=round(t, 3), clock=self.clock_at(t), kind=kind, voice="pbp" if lead else "analyst",
                   priority=prio or spec.priority, ttl=max(spec.ttl, flight + wait), params=params, evidence=[ev_i], layer=layer,
                   voice_wait=max(spec.wait, flight) + wait)
        self.out.append(m)
        return m

    def fast(self, kind: str, t: float, eid: int, team: str, params: dict, ev_i: int, flight: float = 0.0, prio: int | None = None,
             wait: float = 0.0) -> bool | None:
        """Name rationing (7.1). A fragment of a rationed kind names a player unless it may go without (`bare_ok`: the ball itself is worth a
        word) and the fragment before it, of the same team, was named: at most one name-less fragment in a row while one team keeps the ball.
        `name_said`: he was named a moment ago, so the wording goes without him, outside the rationing.
        Returns whether it names a player, or None when nothing was built."""
        params = {**params, "team": self.team_name[team], "team_code": team}
        if self.meta.teams[team].gender:  # the squad's gender is known: a fragment may say "il" (render_params, PRONOUNS)
            params["squad"] = self.meta.teams[team].gender
        bare_ok = params.pop("bare_ok", False)
        if kind in RATIONED:
            named = not bare_ok or self.last_fast is None or self.last_fast[0] != team or self.bare_run >= NAMED_EVERY - 1
            if params.get("name_said"):  # he was named a moment ago: the wording goes without him, outside the rationing
                params["named"] = named = False
            else:
                params["named"] = named
                self.bare_run = 0 if named else self.bare_run + 1
                self.last_fast = (team, named)
        else:
            named = True
            self.bare_run = 0
            self.last_fast = (team, named)
        if self._emit(FAST, FAST_BASE, kind, t, eid, params, ev_i, "fast", flight, prio, wait) is None:
            return None
        if named:
            for key in ("player", "target", "winner", "presser", "taker"):
                if key in params:
                    self.named_at[params[key]] = t
        return named

    def settle(self, now: float, keep: bool = False) -> None:
        """A receipt is called once the receiver has kept the ball for TOUCH_SETTLE_S. The next record that moves the ball (a first-time pass, a
        carry, a shot) before that voids it: that action is the news, and the name is not said twice. `keep`: a record that does not move the ball."""
        due = self.touch_due
        if due is None:
            return
        if due[0] < now - (SCENE_TOUCH_GAP_S if self.scene_at is not None and due[0] >= self.scene_at else 0.0):
            self.touch_due = None
            t, eid, team, params, ev_i, where = due
            self.fast("touch", t, eid, team, params | self.place_at_zone(t, *where), ev_i)
        elif not keep:
            self.touch_due = None

    def place_at_zone(self, t: float, team: str, period: int, x: float, y: float) -> dict[str, str]:
        """The pitch zone of a receiver, only on a rare turn: not within PLACE_EVERY_S of the last readout and never the zone just said."""
        zone = self.place(team, period, x, y)
        if t - self.place_at < PLACE_EVERY_S or (zone["third"], zone["wing"]) == self.place_last:
            return {}
        self.place_at, self.place_last = t, (zone["third"], zone["wing"])
        return zone

    # ---------- records ----------
    def on_event(self, e: Event) -> None:
        if e.type in (EventType.POSSESSION_CHANGE, EventType.TACKLE):
            self.reset_streak()
            self.chain, self.chain_team = [], None
            self.last_fast = None  # a turnover: the side that wins the ball is named, whatever was said before (the rationing is for one side keeping it)
            if e.type is EventType.TACKLE:
                self.touch_player(e.player, e.team, e.t)
                if e.player is not None:
                    self.named_at[self.names[e.player]] = e.t  # the skeleton's tackle call names him
                if e.outcome == "won":
                    self.won_n[e.team] += 1
        elif e.type is EventType.CARD:
            self.stop(e.t, 16 * e.i, e.team, e.player)

    def on_pressure(self, e: Event) -> None:
        """A skeleton pressure event: the presser is the event's player, the pressed one is whoever has the ball (opponent) right now."""
        if self.holder is None or self.holder_team == e.team or e.player is None:
            return
        # "high" only where the presser stands in the opponent's half; elsewhere the line makes no claim about the height (7.5)
        x, _ = _att(e.team, e.period, e.x, e.y)
        facet = "high" if x >= PRESS_HIGH_X else "low"
        self.fast("press_on", e.t, 16 * e.i, e.team, {"presser": self.names[e.player], "player": self.names[self.holder], "facet": facet}, e.i)

    def touch_player(self, pid: str | None, team: str, t: float) -> None:
        if pid is None:
            return
        self.holder, self.holder_team = pid, team
        self.last_touch[pid] = t
        if self.chain_team != team:  # the other side has the ball: a new move
            self.chain, self.chain_team = [], team
        if not self.chain or self.chain[-1] != pid:
            self.chain.append(pid)

    def reset_streak(self) -> None:
        self.streak = {"H": 0, "A": 0}
        self.streak_told = {"H": 0, "A": 0}

    def stop(self, t: float, eid: int, team: str, pid: str | None, goal: bool = False) -> None:
        """Play has stopped at `t`: a slot every DEAD_STEP_S from t + 1 s is offered if nothing happens before it. After a goal the side that
        conceded gets no player note (no clean-sheet trivia about its keeper right after the goal)."""
        self.attack_on = False
        long_team = max(("H", "A"), key=lambda side: self.streak[side])
        if self.streak[long_team] >= SPELL_MIN_PASSES and not goal and not self.streak_told[long_team]:  # the move that has just ended is worth a sentence in the dead ball
            self.news.append({"t": t, "facet": "spell_end", "team": long_team, "n": self.streak[long_team], "long_only": True})
        self.reset_streak()
        exclude = ("A" if team == "H" else "H") if goal else None
        offsets = tuple((GOAL_QUIET_S if goal else 1.0) + DEAD_STEP_S * k for k in range(DEAD_SLOTS))
        self.pending = [_Slot(t + off, True, eid, pid or self.holder, team, exclude=exclude) for off in offsets]

    def on_row(self, r: dict, t: float) -> None:
        ty, ev_i, team = r["type"], r["i"], r["team"]
        e = self.ev_by_i[ev_i]
        if ty == "pass":
            actor = r.get("player") or e.player
            ptype = r["pass_type"]
            x0, y0 = r.get("x", e.x), r.get("y", e.y)
            self.geom[r["eid"]] = (x0, y0, r.get("end_x", e.end_x), r.get("end_y", e.end_y), e.period, team)
            self.touch_player(actor, team, t)
            self.pass_actor[r["eid"]] = actor
            self.pass_n[team] += 1
            if ptype == "throw_in":
                self.throw_n[team] += 1
            elif ptype == "goal_kick":
                self.gk_n[team] += 1
            if ptype == "cross":
                self.cross_n[team] += 1
            elif ptype == "long":
                self.long_n[team] += 1
            if ptype == "corner":
                self.corner_n[team] += 1
                q = self.corners[team]
                q.append(t)
                while q and q[0] < t - CORNER_WINDOW_S:
                    q.popleft()
                if len(q) >= 3:
                    self.news.append({"t": t, "facet": "corners", "team": team, "nth": min(len(q), 8), "sh": self.shots[team]})
            if ev_i not in self.taken or r.get("implicit"):  # a skeleton moment (the corner call) already owns this kick
                player = self.names[actor]
                if ptype in RESTART_TYPES:
                    side = self.side_of(team, e.period, x0, y0)
                    self.fast("restart", t, r["eid"], team, {"facet": ptype, "side": side}, ev_i)
                elif ptype == "free_kick":
                    if r.get("distance_m", 99.0) <= FREE_KICK_RANGE_M:
                        self.fast("setpiece_setup", t, r["eid"], team, {"taker": player, "foot": r["body_part"]}, ev_i)
                    else:
                        self.fast("restart", t, r["eid"], team, {"facet": "free_kick"}, ev_i)
                elif ptype != "corner":  # every kick is a fragment: who plays it (and to whom, for a pass with a type), and what kind of pass; the receipt names the receiver
                    if ptype in ("short", "back") and r.get("first_time"):
                        ptype = "first_time"
                    # the fragment stays worth saying while the ball is in the air (t_arr is visible at the kick, 4.2)
                    flight = min(max(r["t_arr"] - t + 0.2, 0.0), MAX_FLIGHT_TTL_S)
                    params = {"player": player}
                    if self.named_at.get(player, -1e9) > t - NAME_GAP_S:  # his receipt, a tackle or a duel named him a moment ago: the kick does not say it again
                        params["kicker_said"] = True
                    if ptype not in ROUTINE_PASS:
                        params["arr"] = round(r["t_arr"], 3)
                    if ptype != "clearance" and ptype not in ROUTINE_PASS:  # a clearance is not for anyone; a routine kick names the kicker only, the receipt names the receiver
                        params["target"] = self.names[r["target"]]
                    if ptype in ROUTINE_PASS:
                        # a short pass is the kicker with what the kick shows: he is closed down, or he hits it hard and low (never a verdict, never the path)
                        if r["pressure"].get("under"):
                            params["pressed"] = True
                        elif r.get("height") == "driven":
                            params["driven"] = True
                    else:  # `lane` is where the kick starts (the flank it leaves from), never the path of the ball; a typed pass is finished when the ball lands
                        params |= {"pass_type": ptype, "lane": self.side_of(team, e.period, x0, y0), "bare_ok": ptype in BARE_PASS}
                    if self.scene_at is not None and t >= self.scene_at and e.outcome == "incomplete" and ptype in ROUTINE_PASS:
                        pass  # a scene: a short pass that is cut out is not called "plays it on"; the interception's call has the moment
                    elif ptype in ROUTINE_PASS:
                        # a routine kick whose kicker was named a moment ago (his receipt just did) is not called: it would name him twice or say nothing the
                        # listener lacks. The receipt names the receiver and never the kicker again.
                        self.split_kicks.add(r["eid"])
                        if not params.get("kicker_said"):
                            self.fast("pass_kind", t, r["eid"], team, params, ev_i, flight)
                        elif ("pressed" in params or "driven" in params) and t - self.shown_at >= SHOWN_GAP_S:  # what the kick shows, without his name, now and then
                            if self.fast("pass_kind", t, r["eid"], team, params | {"name_said": True}, ev_i, flight) is not None:
                                self.shown_at = t
                    elif self.fast("pass_kind", t, r["eid"], team, params, ev_i, flight,
                                   *((SCENE_FINAL_PRIO, SCENE_FINAL_WAIT_S) if self.scene_at is not None and t >= self.scene_at and ptype in SCENE_FINAL_TYPES
                                     else (None, 0.0))) and "target" in params:
                        self.kicked.add(r["eid"])  # a pass named with its target ("Long ball for Tavares"): the receipt need not name him again
            if e.outcome == "out" and not r.get("implicit"):  # the ball leaves at its arrival: a dead ball from then on
                self.stop(r["t_arr"], r["eid"], team, actor)
        elif ty == "receipt":
            pid = r["player"]
            self.touch_player(pid, team, t)
            kicker = self.pass_actor.get(r["pass_eid"])
            if kicker is not None:
                self.passes_done[kicker] = self.passes_done.get(kicker, 0) + 1
            self.completed[team].append(t)
            self.streak[team] += 1
            self.streak["A" if team == "H" else "H"] = 0
            self.streak_told["A" if team == "H" else "H"] = 0
            spell = t - self.last_touch.get(pid, t)
            self.last_touch[pid] = t
            if self.streak[team] in (10, 15, 20) and self.streak[team] > self.streak_best[team] and self.streak_lines < STREAK_MAX:
                self.streak_best[team] = self.streak[team]  # a streak is news when it is longer than the last one of this side, and a match has a few
                self.streak_lines += 1
                self.streak_told[team] = self.streak[team]
                self.news.append({"t": t, "facet": "passes" if self.streak_lines % 2 else "passes_2", "team": team, "n": self.streak[team]})
            if spell > SPELL_S:
                self.news.append({"t": t, "facet": "spell", "team": team, "player": pid})
            g = self.geom.get(r["pass_eid"])
            if g is not None and (r["touch"] != "control" or r["pass_eid"] not in self.kicked):
                # `dir` is how the ball arrived (the incoming pass), which the wordings say as "Forward to X"; it is never the receiver's next action.
                # The kick fragment named him if it was named; a receipt then speaks only for a ball worth a word (chest, head) and, once the receiver
                # has kept it for TOUCH_SETTLE_S (`settle`), with the zone only on a rare turn
                params = {"player": self.names[pid], "dir": self.direction(g), "facet": r["touch"], "facing": r["facing"],
                          "bare_ok": r["touch"] != "control" or r["facing"] == "own_goal"}
                if r["pass_eid"] in self.kicked:  # the kick named both of them: a receipt worth a word says the touch, not who played it to whom
                    del params["dir"]
                elif kicker is not None and r["pass_eid"] not in self.split_kicks and self.named_at.get(self.names[kicker], -1e9) <= t - NAME_GAP_S:  # a split kick named the kicker: he is not named again
                    params["kicker"] = self.names[kicker]
                settle_s = TOUCH_SETTLE_S
                if self.scene_at is not None and t >= self.scene_at:  # a scene: a quick ball on is the news (a cross, a cutback), and a headed
                    settle_s = SCENE_HEAD_SETTLE_S if r["touch"] == "head" else SCENE_SETTLE_S  # finish is called as the goal, never as "heads it on"
                self.touch_due = (t + settle_s, r["eid"], team, params, ev_i, (team, g[4], r["x"], r["y"]))
            self.pending = [_Slot(t + CONTEXT_FIRST_HOLD_S, False, r["eid"], pid, team),
                            _Slot(t + SECOND_HOLD_S, False, r["eid"], pid, team, long=True)]
        elif ty == "carry":
            actor = r.get("player") or e.player
            self.touch_player(actor, team, t)
            rationed = self.attack_on and t - self.carry_said < SCENE_CARRY_GAP_S  # a scene's attack: one carry line, the voice stays free for the ball in
            if r.get("progress_m", 0.0) >= CARRY_MIN_PROGRESS_M and (ev_i not in self.taken or r.get("implicit")) and not rationed:
                self.carry_said = t
                said = self.named_at.get(self.names[actor], -1e9) > t - NAME_GAP_S
                self.fast("carry", t, r["eid"], team, {"player": self.names[actor], "bare_ok": True, "name_said": said}, ev_i)
        elif ty == "interception":
            if self.scene_at is not None and t >= self.scene_at:
                self.attack_on = True
            self.touch_player(e.player, team, t)
            self.reset_streak()
            self.last_fast = None
            self.won_n[team] += 1
            if ev_i in self.taken and e.player is not None:
                self.named_at[self.names[e.player]] = t  # the skeleton's call names the winner
            if ev_i not in self.taken:
                self.fast("duel", t, r["eid"], team, {"winner": self.names[e.player], "facet": "interception", "bare_ok": True}, ev_i)
        elif ty == "shot":
            self.reset_streak()
            self.shots[team] += 1
            self.shot_t[team].append(t)
            self.last_shot_t[team] = t
            if e.outcome in ("saved", "goal"):
                self.on_target_n[team] += 1
            if e.outcome == "saved":
                self.saves_n["A" if team == "H" else "H"] += 1
            if self.shots[team] in (3, 5, 8):
                self.news.append({"t": t, "facet": "shots", "team": team, "nth": self.shots[team], "so": self.shots["A" if team == "H" else "H"]})
            if e.outcome == "goal":
                self.goals[team] += 1
                self.on_goal(r, e, t, team)
            elif e.player is not None:
                self.on_chance(e, t, team)
            if e.outcome in ("off_target", "goal"):  # a saved shot or one off the post may be followed by play: not a stoppage
                self.stop(t, r["eid"], team, e.player, goal=e.outcome == "goal")
        elif ty == "foul":
            self.foul_n[team] += 1
            n = self.fouls[e.player] = self.fouls.get(e.player, 0) + 1
            if n >= 3:
                self.news.append({"t": t, "facet": "fouls", "team": team, "player": e.player, "nth": min(n, 8), "m": self.foul_n[team]})
            self.stop(t, r["eid"], team, e.player)
        elif ty == "take_on" and ev_i not in self.taken:  # lost take-ons share their event with a skeleton tackle call: silent until tracking
            self.fast("take_on", t, r["eid"], team, {"player": self.names[r["player"]], "defender": self.names[r["defender"]],
                                                     "facet": r["outcome"]}, ev_i)

    def move_before(self, scorer: str | None) -> list[str]:
        """The last three players of the move before the shooter, oldest first (the shooter himself is not in it)."""
        before: list[str] = []
        for pid in reversed(self.chain):
            if pid != scorer and pid not in before and len(before) < 3:
                before.insert(0, pid)
        return before

    def on_goal(self, r: dict, e: Event, t: float, team: str) -> None:
        """The scorer's and the assister's season numbers move with the goal (the profile's numbers are from before the match, 1.1). The goal is news
        in the dead ball after it: first the move that led to it, then the scorer's tally (`NEWS_RANK`)."""
        if e.player is None:
            return
        self.match_goals[e.player] = self.match_goals.get(e.player, 0) + 1
        assist = self.pass_actor.get(r.get("assist_eid"))
        if assist is not None:
            self.match_assists[assist] = self.match_assists.get(assist, 0) + 1
        before = self.move_before(e.player)
        if before and self.chain_team == team:
            self.news.append({"t": t, "facet": "move", "team": team, "player": e.player, "chain": before,
                              "goals_h": self.goals["H"], "goals_a": self.goals["A"]})
        p = self.players.get(e.player)
        if p is not None and p.season is not None:
            total = p.season.goals + self.match_goals[e.player]
            news = {"t": t, "facet": "tally" if total > 1 else "tally_first", "team": team, "player": e.player, "n": total}
            if assist is not None and assist != e.player:
                news["assist"] = assist
            self.news.append(news)

    def on_chance(self, e: Event, t: float, team: str) -> None:
        """A shot that was not a goal, with the move that led to it: a sentence for a dead ball or a long hold (it needs the time)."""
        before = self.move_before(e.player)
        facet = {"saved": "chance_saved", "off_target": "chance_off", "blocked": "chance_blocked", "post": "chance_post"}.get(e.outcome or "")
        if before and self.chain_team == team and facet is not None:
            news = {"t": t, "facet": facet, "team": team, "player": e.player, "chain": before, "long_only": True}
            if e.keeper is not None:
                news["keeper"] = e.keeper
            self.news.append(news)

    @staticmethod
    def direction(g: tuple[float, float, float, float, int, str]) -> str:
        """forward | back | inside | wide: where a pass (an entry of `geom`) goes, in the passing side's attacking direction."""
        (x0, y0), (x1, y1) = _att(g[5], g[4], g[0], g[1]), _att(g[5], g[4], g[2], g[3])
        return "forward" if x1 - x0 >= TOUCH_DIR_M else "back" if x1 - x0 <= -TOUCH_DIR_M else \
            "inside" if abs(y1 - PITCH_W / 2) < abs(y0 - PITCH_W / 2) else "wide"

    @staticmethod
    def place(team: str, period: int, x: float, y: float) -> dict[str, str]:
        """Where a player stands, in his side's attacking direction: `third` (own, mid, final) and `wing` (left, centre, right)."""
        ax, ay = _att(team, period, x, y)
        return {"third": "own" if ax < THIRD_X[0] else "mid" if ax < THIRD_X[1] else "final", "wing": SIDES[(ay >= PITCH_W / 3) + (ay > 2 * PITCH_W / 3)]}

    def side_of(self, team: str, period: int, x: float, y: float) -> str:
        _, ay = _att(team, period, x, y)
        return "left" if ay < PITCH_W / 3 else "right" if ay > 2 * PITCH_W / 3 else "centre"

    # ---------- context slots ----------
    def flush(self, now: float, keep: bool = False) -> None:
        """Offer every slot whose time has come before `now`: nothing happened in between, or the slot would have been voided.
        The slots that are not due yet are void too, unless `keep` (a record that does not move the ball)."""
        due = sorted((s for s in self.pending if s.t < now), key=lambda s: s.t)
        self.pending = [s for s in self.pending if s.t >= now] if keep else []
        for s in due:
            self.offer(s)

    def cooled(self, kind: str, team: str, t: float) -> bool:
        return t - self.cool.get((kind, team), -1e9) >= HOLD_COOLDOWN_S.get(kind, 0.0)

    def tactic_free(self, side: str, t: float) -> bool:
        """The shape, the press and the phase of one side say much the same ("dropped deep", "happy to let the ball go", "sit in a low block"):
        one of them per TACTIC_GAP_S. A change that has to wait stays unseen, so it is said when the gap is over if it still holds."""
        return t - self.tactic_at[side] >= TACTIC_GAP_S

    TOPIC_KIND = {"counter": "counter_note", "fatigue": "fatigue_note", "player": "player_note", "tempo": "tempo_note",
                  "shape": "shape_note", "press": "press_note", "phase": "phase_note", "story": "story_note"}
    HOLD_TOPICS = ("story", "fatigue", "player", "tempo", "shape", "press", "phase", "counter")  # a receiver holds the ball: news about him first, the match facts are kept for the dead ball
    DEAD_TOPICS = ("counter", "story", "shape", "press", "tempo", "phase", "fatigue", "player")  # a dead ball: the match first

    def offer(self, s: _Slot) -> None:
        """Fill a slot with the first topic that has something to say. A topic is asked only when it is its turn (asking marks its
        fact as said), and the kind that was said last goes to the back of the line so two lines of one kind do not follow each other.
        The director voices a context line at most once per CONTEXT_PLAY_S in play and per CONTEXT_DEAD_S in a dead ball, three to a dead-ball
        window: a slot that breaks those is not offered at all, so no fact is used up on a line the voice would drop."""
        if s.t - self.ctx_last < (CONTEXT_DEAD_S if s.dead else CONTEXT_PLAY_S) + SLOT_SLACK_S - 1e-9:
            return
        if self.attack_on and not s.dead:  # a scene's winning move: the play-by-play has the floor
            return
        if s.dead and self.ctx_window.get(s.window, 0) >= CONTEXT_PER_WINDOW:
            return
        order = list(self.DEAD_TOPICS if s.dead else self.HOLD_TOPICS)
        goal_news = any(NEWS_RANK.get(n["facet"], 2) < 2 for n in self.news)  # the move and the tally of a goal follow each other, whatever was said last
        order.sort(key=lambda n: self.TOPIC_KIND[n] == self.last_topic and not goal_news)  # stable: only the repeat moves
        for name in order:
            pick = getattr(self, f"topic_{name}")(s)
            if pick is None:
                continue
            kind, params = pick
            params = {**params, "dead": s.dead, "window": s.window, "long": s.dead or s.long}
            ev_i = self.events[max(0, bisect.bisect_right(self.ev_t, s.t) - 1)].i
            if self._emit(CONTEXT, CONTEXT_BASE, kind, s.t, round(10 * s.t), params, ev_i, "context") is not None:
                self.last_topic = kind
                self.ctx_last = s.t
                self.ctx_times.append(s.t)
                if s.dead:
                    self.ctx_window[s.window] = self.ctx_window.get(s.window, 0) + 1
                self.cool[(kind, params["team_code"])] = s.t
                if kind in TACTIC_KINDS:
                    self.tactic_at[params["team_code"]] = s.t
                    self.idea_said.add((params["team_code"], TACTIC_IDEA[params["facet"]]))
            return

    def fresh_news(self, s: _Slot) -> dict | None:
        """The news for a slot: the goal's move, then its tally, then the rest in order of time. Each is used once in a match (the key holds what
        makes it this one: the score a goal made, the players of the move, the number), and a sentence that
        needs the time of a dead ball (a chance with the move behind it) waits for one."""
        self.news = [n for n in self.news if s.t - n["t"] <= NEWS_TTL_S]
        for n in sorted((n for n in self.news if s.dead or s.long or not n.get("long_only")), key=lambda n: (NEWS_RANK.get(n["facet"], 2), n["t"])):
            minor = n["facet"] in MINOR_NEWS
            if minor and (s.t - self.minor_at < MINOR_GAP_S or self.news_n.get(n["facet"], 0) >= NEWS_MAX.get(n["facet"], 99)):
                continue  # a figure waits for its turn (it is dropped when it is stale) and a kind has its few lines per match
            self.news.remove(n)
            key = (n["facet"], n["team"], n.get("player"), n.get("n"), n.get("nth"), tuple(n.get("chain", ())), n.get("goals_h"), n.get("goals_a"))
            if key not in self.news_said:  # the third corner in five minutes can come twice in a match, the sentence not; a scorer's second goal has its own move
                self.news_said.add(key)
                if minor:
                    self.minor_at = s.t
                    self.news_n[n["facet"]] = self.news_n.get(n["facet"], 0) + 1
                return n
        return None

    def _ctx(self, team: str, **params) -> dict:
        return {"team": self.team_name[team], "team_code": team, "other": self.team_name["A" if team == "H" else "H"], **params}

    def topic_counter(self, s: _Slot):
        n = self.fresh_news(s)
        if n is None:
            return self.topic_state(s)
        params = self._ctx(n["team"], facet=n["facet"])
        for key in ("nth", "n", "m", "sh", "so", "goals_h", "goals_a"):
            if key in n and not (key in ZEROABLE and n[key] == 0):
                params[key] = n[key]
        if n["facet"] == "shots":  # "That is Marlow's third shot, and Tamsworth have had nine" says the figures of the shots stat: it waits for a new shot
            for side in ("H", "A"):
                self.stat_said[("shots_total", side)] = (s.t, max(self.shots[side], self.stat_said.get(("shots_total", side), (0.0, 0))[1]))
        if n["facet"] in ("tally", "tally_first"):  # the scorer's season goals were just said: his player note does not say them again
            self.said_facets.setdefault(n["player"], {})["season"] = s.t
        for key in ("player", "assist", "keeper"):
            if key in n:
                params[key] = self.names[n[key]]
        if "chain" in n:
            params["chain"] = [self.names[pid] for pid in n["chain"]]
        return "counter_note", params

    def topic_state(self, s: _Slot):
        """Game state, the topic real commentary returns to (COMMENTATOR.md): the score and the clock, when the score has changed or five match
        minutes have passed since it was last said, never twice within a minute and not before the tenth minute unless a goal moved the score.
        The wording takes turns, and in added time it says "added time" instead of a minute that stands still at 45 or 90."""
        score = (self.goals["H"], self.goals["A"])
        since = s.t - self.state_at
        minute = self.minute_at(s.t)
        moved = score != self.state_score and since >= STATE_GAP_S
        if not (moved or (since >= STATE_STEP_S and minute >= STATE_FROM_MIN)):
            # the match facts wait for a dead ball or a long hold, which have the time for the long sentence: a short one in play would take the voice from the play
            return self.topic_stats(s, minute) if s.dead or s.long else None
        self.state_at, self.state_score = s.t, score
        added = "+" in self.clock_at(s.t)
        h, a = score
        lead = "H" if h > a else "A"
        base, team = ("goalless", s.team) if h == a == 0 else ("level", s.team) if h == a else ("lead", lead)
        self.state_turn += 1
        facet = f"{base}_added" if added else base if self.state_turn % 2 else f"{base}_2"
        other = "A" if team == "H" else "H"
        params = self._ctx(team, facet=facet, **{k: v for k, v in (("sh", self.shots[team]), ("so", self.shots[other])) if v})
        if not added:
            params["n"] = minute
        return "counter_note", params

    def stat_values(self, t: float) -> dict[str, dict[str, int]]:
        """Every match fact `topic_stats` can say, per side, as it stands at `t`."""
        total = max(1, self.pass_n["H"] + self.pass_n["A"])
        for side in ("H", "A"):  # the last three minutes of completed passes, as the tempo notes count them
            q = self.completed[side]
            while q and q[0] < t - TEMPO_WINDOW_S:
                q.popleft()
        recent = {side: len(self.completed[side]) for side in ("H", "A")}
        recent_total = recent["H"] + recent["A"]
        share = round(100 * recent["H"] / recent_total) if recent_total >= RECENT_MIN_PASSES else 50
        held = {"H": share, "A": 100 - share} if 0 < share < 100 else {"H": 0, "A": 0}  # the two shares add up to a hundred; a side with all of the ball is no figure a number word holds
        poss_h = min(99, round(100 * self.pass_n["H"] / total))
        return {"shots_total": self.shots, "corners_total": self.corner_n, "fouls_total": self.foul_n,
                "possession": {"H": poss_h, "A": 100 - poss_h},
                "crosses_total": self.cross_n, "long_total": self.long_n, "won_back_total": self.won_n, "on_target_total": self.on_target_n,
                "saves_total": self.saves_n, "throws_total": self.throw_n, "goal_kicks_total": self.gk_n,
                "recent_ball": held,
                "drought": {side: int((t - self.last_shot_t[side]) // 60) for side in ("H", "A")}}

    def topic_stats(self, s: _Slot, minute: int):
        """The match so far in one fact per line (shots, corners, fouls, the ball, the restarts, a side's spell without a shot), each team's value
        only when it has grown, at most STAT_MAX times per team and fact, and the wording takes turns, so no line comes back word for word."""
        if minute < 8 or s.t - self.minor_at < MINOR_GAP_S:
            return None
        values = self.stat_values(s.t)
        for k in range(2 * len(STAT_FACETS)):  # rotate, so the same fact does not always go first
            facet = STAT_FACETS[(self.stat_turn + k) % len(STAT_FACETS)]
            for team in (s.team, "A" if s.team == "H" else "H"):
                value = values[facet][team]
                last_t, last_v = self.stat_said.get((facet, team), (-1e9, 0))
                done = self.stat_count.get((facet, team), 0)
                if value < STAT_FLOOR.get(facet, 3) or s.t - last_t < STAT_GAP_S or value < last_v + STAT_STEP.get(facet, 1) or done >= STAT_MAX_BY.get(facet, STAT_MAX):
                    continue
                other = "A" if team == "H" else "H"
                m = values[facet][other]
                if facet == "drought":  # the other side's shots in the time this side has been without one
                    m = sum(1 for x in self.shot_t[other] if x > self.last_shot_t[team])
                    if m == 0:  # neither side has shot: nothing to set it against
                        continue
                self.stat_said[(facet, team)] = (s.t, value)
                self.stat_count[(facet, team)] = done + 1
                for f in STAT_TWINS.get(facet, (facet,)):  # the long sentence says both sides' figures, and a shot on target is a save for the other keeper: the twin is said
                    for side in ("H", "A"):
                        if (f, side) != (facet, team):
                            self.stat_said[(f, side)] = (s.t, max(values[f][side], self.stat_said.get((f, side), (0.0, 0))[1]))
                self.stat_turn += 1
                self.minor_at = s.t
                params = self._ctx(team, facet=facet if done % 2 == 0 else f"{facet}_2", n=value)
                if m:
                    params["m"] = m
                return "counter_note", params
        return None

    def topic_fatigue(self, s: _Slot):
        p = self.players.get(s.holder or "")
        if p is None or s.t < FATIGUE_MIN_T or p.group == "GK" or p.id in self.fatigue_said or fatigue_base(p, s.t) < FATIGUE_AT:
            return None
        self.fatigue_said.add(p.id)
        return "fatigue_note", self._ctx(s.team, player=self.names[p.id])

    def _facets(self, p: Player) -> list[str]:
        facets = [f"trait:{t.value}" for t in (p.traits or [])]
        if p.role is not None and p.role.value in NOTABLE_ROLES:
            facets.append(f"role:{p.role.value}")
        se = p.season
        if se is not None:
            if se.goals + self.match_goals.get(p.id, 0) >= 3 and p.group in ("MID", "FWD"):
                facets.append("season")
            if se.assists + self.match_assists.get(p.id, 0) >= 3 and p.group in ("MID", "FWD"):
                facets.append("assists")
            if (se.clean_sheets or 0) >= 4 and p.group in ("GK", "DEF"):
                facets.append("clean_sheets")
            facets.append("apps")
        if p.captain:
            facets.append("captain")
        if (p.age or 0) >= 31:
            facets.append("veteran")
        if (p.age or 99) <= 21:
            facets.append("youngster")
        if p.foot == "L" and p.group != "GK":
            facets.append("lefty")
        if p is self.tallest:
            facets.append("tallest")
        done = self.passes_done.get(p.id, 0)
        if PASSES_MIN <= done <= PASSES_MAX and not any(f.startswith("passes:") for f in self.said_facets.get(p.id, {})):  # live: said once per player, or only the number would move
            facets.append(f"passes:{done // PASSES_STEP}")
        return facets

    def _facet_numbers(self, p: Player, facet: str, suffix: str = "") -> tuple[str, dict]:
        """The name of a player-note facet as WORDS knows it, and the numbers its clause needs (`suffix` keeps the second fact's apart)."""
        se = p.season
        if facet == "season":
            return facet, {f"season_goals{suffix}": se.goals + self.match_goals.get(p.id, 0)}
        if facet.startswith("passes:"):
            return "passes", {f"count{suffix}": self.passes_done[p.id]}
        if facet in ("assists", "clean_sheets", "apps"):
            return facet, {f"count{suffix}": {"assists": se.assists + self.match_assists.get(p.id, 0), "clean_sheets": se.clean_sheets,
                                              "apps": se.apps + 1}[facet]}
        return facet, {}

    def topic_player(self, s: _Slot):
        """A note on the player on the ball, or in a dead ball on whoever touched it lately: a fact about a player is said once in the
        match (word for word it never comes back), the same player not again within PLAYER_GAP_S, and never the same kind of fact twice in a
        row (three clean-sheet notes after each other). Season numbers are from before the match, so the goals and assists he has
        scored in it so far are added, and this match counts as an appearance. A dead ball has the time for a second fact of the same
        player in the same sentence ("is left-footed and wears the armband"); it counts as said too."""
        pool = [s.holder] if not s.dead else sorted(self.last_touch, key=lambda pid: -self.last_touch[pid])
        roomy = s.dead or s.long  # a dead ball has the time for a sentence of two or three facts: whoever has them goes first
        if not roomy and s.t - self.play_note_at < PLAY_NOTE_GAP_S:  # a one-fact note while he holds the ball is rare: it would take the slot of the long sentence a longer hold has room for
            return None
        for need in (2, 1) if roomy else (1,):
            for pid in pool:
                p = self.players.get(pid or "")
                if p is not None and self.team_of.get(p.id) == s.exclude:
                    continue
                if p is None or s.t - self.note_at.get(p.id, -1e9) < PLAYER_GAP_S:
                    continue
                seen = self.said_facets.setdefault(p.id, {})
                facets = self._facets(p)
                facet = next((f for f in facets if f not in seen and _family(f) != _family(self.last_facet or "")), None)
                if facet is None:
                    continue
                more: list[str] = []  # the same player's other facts, for the same sentence; they count as said too
                for f in facets if roomy else ():
                    if len(more) < 2 and f not in seen and f != facet and all(_family(f) != _family(g) for g in [facet, *more]) \
                            and not (f in SEASONAL and any(g in SEASONAL for g in [facet, *more])):  # two "this season" facts in one sentence read badly
                        more.append(f)
                if len(more) + 1 < need:
                    continue
                seen[facet] = s.t
                if not roomy:
                    self.play_note_at = s.t
                self.last_facet = facet
                self.note_at[p.id] = s.t
                team = "H" if p in self.meta.teams["H"].players else "A"
                params = self._ctx(team, player=self.names[p.id])
                params["facet"], numbers = self._facet_numbers(p, facet)
                params |= numbers
                for k, f in enumerate(more, start=2):
                    seen[f] = s.t
                    params[f"facet{k}"], numbers_k = self._facet_numbers(p, f, str(k))
                    params |= numbers_k
                return "player_note", params
        return None

    def topic_story(self, s: _Slot):
        """A story from the dossier for a quiet spell: the player on the ball first (an old club, a milestone, the goal in the last meeting),
        then his side or the other (the form, the table, the coach, comebacks, a home run). Only when there is time for a sentence (a dead ball
        or a long hold), at most one per STORY_GAP_S, each story once a match, the best one first. Not in the first minutes: the booth sets
        the scene with the play first."""
        if not (s.dead or s.long) or s.t - self.story_at < STORY_GAP_S or s.t < STORY_FROM_S:
            return None
        span, most = STORY_ROOM
        if sum(1 for x in self.ctx_times if s.t - x < span) >= most:
            return None
        d = self.dossier
        pool = [x for x in d.for_player(s.holder or "")] if s.holder else []
        pool += [x for x in d.stories if x.kind == "last_meeting" and x.data.get("scorer_id") == s.holder]
        pool += d.for_side(s.team) + d.for_side("A" if s.team == "H" else "H")
        pool = [x for x in pool if x.id not in self.story_said and x.side != s.exclude and self.story_fits(x, s.t)]
        if not pool:
            return None
        best = max(pool, key=lambda x: x.weight + (0.3 if x.player and x.player == s.holder else 0)
                   + (0.3 if x.kind == "last_meeting" and x.data.get("scorer_id") == s.holder else 0))
        self.story_said.add(best.id)
        self.story_at = s.t
        return "story_note", self._ctx(best.side, **story_params(best))

    def story_fits(self, st, t: float) -> bool:
        """Some stories belong to a moment of the match, not to any quiet spell: "they have come from behind before" is told when that side
        is behind in the second half, the form of a side when the score says something about it (behind, or level late on)."""
        side, other = st.side, "A" if st.side == "H" else "H"
        behind = self.goals[side] < self.goals[other]
        if st.kind == "comebacks":
            return behind and t >= COMEBACK_STORY_T
        if st.kind == "form":
            return behind or self.goals[side] > self.goals[other] or t >= COMEBACK_STORY_T
        return True

    def _class_tempo(self, team: str, t: float) -> str:
        """slow | high | measured: the pass rate of one side over the last three minutes, for the side that has the ball. A side that lacks the
        ball does not slow the game down, it is under siege (and both sides cannot have it), so a claim needs TEMPO_HAS_BALL of the completed
        passes of both sides. Entering a class takes a clearer rate than staying in it, so a rate hovering at a limit does not flip the note."""
        for side in ("H", "A"):
            q = self.completed[side]
            while q and q[0] < t - TEMPO_WINDOW_S:
                q.popleft()
        own, other = len(self.completed[team]), len(self.completed["A" if team == "H" else "H"])
        ppm = own / (TEMPO_WINDOW_S / 60)
        if own + other == 0 or own / (own + other) < TEMPO_HAS_BALL:
            return "measured"
        was = self.tempo_class[team]
        if ppm < (TEMPO_SLOW_EXIT_PPM if was == "slow" else TEMPO_SLOW_PPM):
            return "slow"
        return "high" if ppm > (TEMPO_HIGH_EXIT_PPM if was == "high" else TEMPO_HIGH_PPM) else "measured"

    def topic_tempo(self, s: _Slot):
        if s.t < 300.0:
            return None
        for side in (s.team, "A" if s.team == "H" else "H"):
            cls = self._class_tempo(side, s.t)
            if cls != self.tempo_class[side]:
                self.tempo_class[side] = cls
                if cls != "measured" and s.t - self.tempo_at[side] >= 180.0 and self.tempo_n[side] < TEMPO_MAX:
                    self.tempo_at[side] = s.t
                    self.tempo_n[side] += 1
                    return "tempo_note", self._ctx(side, facet=cls if self.tempo_n[side] == 1 else f"{cls}_2")
        return None

    def _plan(self, side: str, t: float):
        tm = self.meta.teams[side]
        return plan_at(tm.tactics, tm.postures or [], tm.players, t) if tm.tactics is not None else None

    def topic_shape(self, s: _Slot):
        for side in (s.team, "A" if s.team == "H" else "H"):
            if not self.tactic_free(side, s.t):
                continue
            posture, ten = state_at(self.meta.teams[side].postures, s.t)
            old = self.shape_seen[side]
            if (posture, ten) == old:
                continue
            self.shape_seen[side] = (posture, ten)
            facet = "ten_men" if ten and not old[1] else posture if posture in ("chase", "protect") else None
            if facet is not None and (side, TACTIC_IDEA[facet]) not in self.idea_said:
                return "shape_note", self._ctx(side, facet=facet)
        return None

    def topic_press(self, s: _Slot):
        if s.t < 360.0:
            return None
        for side in (s.team, "A" if s.team == "H" else "H"):
            plan = self._plan(side, s.t)
            if plan is None or not self.tactic_free(side, s.t):
                continue
            i = plan.press.intensity
            cls = "intense" if i >= 0.62 else "passive" if i <= 0.35 else "measured"
            if self.press_seen.get(side) != cls:
                self.press_seen[side] = cls
                if cls != "measured" and (side, TACTIC_IDEA[cls]) not in self.idea_said:
                    return "press_note", self._ctx(side, facet=cls)
        return None

    def topic_phase(self, s: _Slot):
        """The out-of-possession team's block (high or low) from the plan, or a counter-minded team that has just won the ball."""
        if s.t < 240.0:
            return None
        other = "A" if s.team == "H" else "H"
        for side, facet in ((other, None), (s.team, "counter")):
            plan = self._plan(side, s.t)
            if plan is None or not self.cooled("phase_note", side, s.t) or not self.tactic_free(side, s.t):
                continue
            f = facet if (facet == "counter" and plan.counter and self.streak[side] <= 2) else (
                plan.block if facet is None and plan.block in ("high", "low") else None)
            if f is not None and (side, TACTIC_IDEA[f]) not in self.idea_said:
                return "phase_note", self._ctx(side, facet=f)
        return None


def build_layers(meta: MatchMeta, events: list[Event], rows: list[dict], scene_at: float | None = None) -> list[Moment]:
    """Every fast and context moment of a match, sorted by time of knowledge. Ids are derived from data (0.2). `scene_at`: a generated live
    scene starts at this match second (see `Layers`); None for every recorded or plain match."""
    return Layers(meta, events, rows, scene_at).run()
