"""Phase 1 of docs/PLAN-DATA.md: player profiles (DATA-MODEL 1.1 to 1.3) and the guarantee that the skeleton did not move."""
import hashlib
from dataclasses import dataclass

import orjson
import pytest

from matchvoice.schema import Attrs, MatchMeta, Role, Trait
from matchvoice.sim.__main__ import write_match
from matchvoice.sim.arcs import ARCS
from matchvoice.sim.engine import Sim
from matchvoice.sim.profile import (
    BOOL_MARGIN, build_player, build_team, flank, role_of, slot_class, trait_margins, traits_of, work_rate_of,
)

SEEDS = range(1, 51)

# SHA-256 of events.jsonl and truth.json written by the code before phase 1 (shasum -a 256 data/matches/*/...)
GOLDEN = {
    ("comeback", 7): ("58d68e06f5ad3de5d9356b94a47aeb43b5e1f8dc00a2223068b44d6b9acf6b41",
                      "245ef08f26eee3cda713439939f8bc9f1e44a648c98c8737b045abb5ace80d99"),
    ("red_card", 7): ("4eec489e407210f9402c9c9888a23073e47ab4a1223acd6ae8360c6d6e620645",
                      "9150976e6e346f2f610a63a3917859ab3173dbdd8429d6cdc1d809a3ac3d588e"),
    ("unlucky", 7): ("b0421c0b3a6498eed1f0b09331cac4c4d1ef4183271d8fb81aabfc0e82586f6b",
                     "544abc94036912dedf7d6b7758aded11396274d4bc48abc0a1f69fbaa3415d97"),
    ("red_card", 11): ("4b91c137e20388c7b9c9937e675150fde5d13a8391a7c714993815cd5e7bcaa6",
                       "e3b7910b29895ec95ba5a0ba07bf7fa59c21b807e0f786ed517b7fab7be47c17"),
}


@pytest.fixture(scope="module")
def runs():
    """Sim object and meta for every arc and seed 1..50."""
    out = {}
    for arc in ARCS:
        for seed in SEEDS:
            sim = Sim(arc, seed)
            meta, _, _ = sim.run()
            out[(arc, seed)] = (sim, meta)
    return out


def attrs(**kw) -> Attrs:
    base = dict(pace=50, passing=50, finishing=50, acceleration=50, dribbling=50, vision=50, defending=50, aerial=50, stamina=50)
    return Attrs(**{**base, **kw})


@dataclass
class Slot:
    id: str
    pos: str
    group: str
    ay: float
    passing: float = 0.5
    finishing: float = 0.5
    pace: float = 0.5


# ---------- the skeleton did not move ----------

@pytest.mark.parametrize("arc,seed", list(GOLDEN))
def test_events_and_truth_bytes_unchanged(tmp_path, arc, seed):
    out = write_match(arc, seed, tmp_path)
    events, truth = GOLDEN[(arc, seed)]
    assert hashlib.sha256((out / "events.jsonl").read_bytes()).hexdigest() == events
    assert hashlib.sha256((out / "truth.json").read_bytes()).hexdigest() == truth


def test_meta_json_round_trips_with_profiles(tmp_path):
    out = write_match("comeback", 7, tmp_path)
    meta = MatchMeta.model_validate(orjson.loads((out / "meta.json").read_bytes()))
    assert all(p.role and p.attrs and p.season for t in meta.teams.values() for p in t.players)
    assert all(t.tactics for t in meta.teams.values())


def test_old_meta_without_profiles_still_loads():
    old = {"id": "x-1", "seed": 1, "arc": "comeback", "title": "t", "competition": "c", "venue": "v", "teams": {
        "H": {"side": "H", "name": "n", "short": "N", "color": "#fff", "formation": "4-4-2",
              "players": [{"id": "H1", "name": "A B", "number": 1, "pos": "GK", "group": "GK"}]}}}
    meta = MatchMeta.model_validate(old)
    assert meta.teams["H"].players[0].role is None and meta.teams["H"].tactics is None


# ---------- profile fields ----------

def test_exported_skill_values_are_the_simulations_own(runs):
    for (arc, seed), (sim, meta) in runs.items():
        for s in ("H", "A"):
            for sp, p in zip(sim.teams[s].players, meta.teams[s].players, strict=True):
                assert p.attrs.pace == round(100 * sp.pace)
                assert p.attrs.passing == round(100 * sp.passing)
                assert p.attrs.finishing == round(100 * sp.finishing)
                assert p.id == sp.id and p.name == sp.name and p.pos == sp.pos


def test_field_ranges_and_shapes(runs):
    for _, meta in runs.values():
        for t in meta.teams.values():
            for p in t.players:
                values = p.attrs.model_dump(exclude={"keeping"}).values()
                assert all(1 <= v <= 99 for v in values)
                assert (p.attrs.keeping is not None) == (p.group == "GK")
                assert p.attrs.keeping is None or 1 <= p.attrs.keeping <= 99
                assert p.foot in ("L", "R", "both")
                assert p.weak_foot == 5 if p.foot == "both" else 2 <= p.weak_foot <= 4
                assert 165 <= p.height_cm <= 198 and 18 <= p.age <= 35
                assert 7.6 <= p.top_speed <= 9.8
                assert p.top_speed == pytest.approx(7.6 + 2.2 * (p.attrs.pace - 30) / 65, abs=0.006)
                assert p.work_rate in ("low", "medium", "high")


def test_season_fields(runs):
    for _, meta in runs.values():
        for t in meta.teams.values():
            for p in t.players:
                s = p.season
                assert 8 <= s.apps <= 36 and 0 <= s.goals <= s.apps and 0 <= s.assists <= s.apps
                assert (s.clean_sheets is not None) == (p.group in ("GK", "DEF"))
                assert s.clean_sheets is None or 0 <= s.clean_sheets <= s.apps


def test_left_slots_favour_the_left_foot(runs):
    def share(pos):
        feet = [p.foot for _, m in runs.values() for t in m.teams.values() for p in t.players if p.pos == pos]
        return sum(f == "L" for f in feet) / len(feet)

    assert share("LB") > share("RB") + 0.12
    assert share("LW") > share("RW") + 0.12
    assert 0.1 < share("RB") < 0.35  # base rate is 0.22


def test_slot_class_and_flank():
    assert [slot_class(p) for p in ("GK", "CB", "RB", "LB", "DM", "CM", "AM", "RM", "LM", "RW", "LW", "ST")] == [
        "GK", "CB", "FB", "FB", "MID", "MID", "MID", "MID", "MID", "W", "W", "ST"]
    assert flank("LB", 8) == "L" and flank("RW", 58) == "R" and flank("ST", 40) == "C"
    assert flank("CB", 26) == "L" and flank("CB", 42) == "R"
    with pytest.raises(ValueError):
        slot_class("XX")


def test_height_follows_the_slot_group(runs):
    def mean(pos):
        h = [p.height_cm for _, m in runs.values() for t in m.teams.values() for p in t.players if p.pos == pos]
        return sum(h) / len(h)

    assert mean("GK") > mean("CB") > mean("ST") > mean("RW")
    assert mean("GK") == pytest.approx(190, abs=1.5) and mean("RB") == pytest.approx(178, abs=1.5)


# ---------- stream isolation and determinism ----------

def test_a_profile_depends_only_on_seed_and_player_id():
    slot = Slot("H5", "LB", "DEF", 8, passing=0.6, finishing=0.4, pace=0.7)
    other = Slot("H5", "LB", "DEF", 8, passing=0.6, finishing=0.4, pace=0.7)
    assert build_player(3, slot, "A B", 3) == build_player(3, other, "A B", 3)
    assert build_player(3, slot, "A B", 3) != build_player(4, slot, "A B", 3)


def test_profile_does_not_touch_the_simulation_generator():
    sim = Sim("unlucky", 5)
    sim.run()
    before = sim.rng.getstate()
    build_team(5, sim.teams["H"].players, [(p.name, p.number) for p in sim.teams["H"].players])
    assert sim.rng.getstate() == before


def test_same_seed_same_profiles():
    a = Sim("red_card", 9).run()[0]
    b = Sim("red_card", 9).run()[0]
    assert a.model_dump() == b.model_dump()


# ---------- roles: table 1.2, first matching rule wins ----------

ROLE_CASES = [
    ("GK", dict(passing=60), "R", 190, "medium", Role.SWEEPER_KEEPER),
    ("GK", dict(passing=59), "R", 190, "medium", Role.SHOT_STOPPER),
    ("CB", dict(passing=62, defending=80, aerial=80), "R", 187, "medium", Role.BALL_PLAYING_CB),
    ("CB", dict(passing=61, defending=72, aerial=65), "R", 187, "medium", Role.STOPPER),
    ("CB", dict(passing=61, defending=71, aerial=65, pace=70), "R", 187, "medium", Role.COVER_CB),
    ("CB", dict(passing=61, defending=72, aerial=64, pace=65), "R", 187, "medium", Role.COVER_CB),
    ("CB", dict(passing=61, defending=71, aerial=64, pace=64), "R", 187, "medium", Role.CENTRE_BACK),
    ("LB", dict(passing=62), "R", 178, "medium", Role.INVERTED_FULLBACK),
    ("RB", dict(passing=62), "L", 178, "medium", Role.INVERTED_FULLBACK),
    ("LB", dict(passing=62), "L", 178, "medium", Role.DEFENSIVE_FULLBACK),
    ("RB", dict(passing=62), "both", 178, "medium", Role.DEFENSIVE_FULLBACK),
    ("LB", dict(passing=61, pace=60, stamina=65), "R", 178, "medium", Role.ATTACKING_FULLBACK),
    ("RB", dict(pace=60, stamina=64), "R", 178, "medium", Role.DEFENSIVE_FULLBACK),
    ("DM", dict(defending=65), "R", 179, "medium", Role.ANCHOR),
    ("DM", dict(defending=64), "R", 179, "medium", Role.DEEP_PLAYMAKER),
    ("CM", dict(passing=68, defending=70, stamina=80), "R", 179, "medium", Role.PLAYMAKER),
    ("CM", dict(passing=67, defending=66, stamina=80), "R", 179, "medium", Role.BALL_WINNER),
    ("CM", dict(passing=67, defending=65, stamina=70), "R", 179, "medium", Role.BOX_TO_BOX),
    ("CM", dict(passing=67, defending=65, stamina=69), "R", 179, "medium", Role.CENTRAL_MIDFIELDER),
    ("AM", dict(finishing=62), "R", 179, "medium", Role.SHADOW_STRIKER),
    ("AM", dict(finishing=61), "R", 179, "medium", Role.ADVANCED_PLAYMAKER),
    ("RM", dict(), "R", 179, "medium", Role.WIDE_MIDFIELDER),
    ("LM", dict(passing=90, finishing=90), "L", 179, "high", Role.WIDE_MIDFIELDER),
    ("RW", dict(), "L", 175, "medium", Role.INVERTED_WINGER),
    ("LW", dict(), "R", 175, "medium", Role.INVERTED_WINGER),
    ("RW", dict(), "R", 175, "medium", Role.WINGER),
    ("LW", dict(), "both", 175, "medium", Role.WINGER),
    ("ST", dict(aerial=68, finishing=80), "R", 186, "high", Role.TARGET_FORWARD),
    ("ST", dict(aerial=68, finishing=65), "R", 185, "medium", Role.POACHER),
    ("ST", dict(aerial=67, finishing=65, stamina=90), "R", 190, "high", Role.POACHER),
    ("ST", dict(finishing=64, stamina=70), "R", 183, "high", Role.PRESSING_FORWARD),
    ("ST", dict(finishing=64, stamina=70), "R", 183, "medium", Role.COMPLETE_FORWARD),
    ("ST", dict(finishing=64, stamina=69), "R", 183, "high", Role.COMPLETE_FORWARD),
]


@pytest.mark.parametrize("pos,kw,foot,height,work,expected", ROLE_CASES)
def test_role_rules(pos, kw, foot, height, work, expected):
    assert role_of(pos, attrs(**kw), foot, height, work) is expected


def test_every_slot_has_a_role_and_every_role_is_reachable(runs):
    seen = {p.role for _, m in runs.values() for t in m.teams.values() for p in t.players}
    assert None not in seen
    assert seen == set(Role)  # measured: all 24 roles occur in the 150 matches, the rarest (target_forward) 15 times


def test_role_cases_cover_every_role():
    assert {c[-1] for c in ROLE_CASES} == set(Role)


def test_work_rate_thresholds():
    assert work_rate_of(80, "FWD") == "high" and work_rate_of(77, "FWD") == "medium"
    assert work_rate_of(76, "MID") == "high" and work_rate_of(75, "MID") == "medium"
    assert work_rate_of(83, "DEF") == "high" and work_rate_of(82, "DEF") == "medium"
    assert work_rate_of(66, "MID") == "medium" and work_rate_of(57, "MID") == "low"
    assert work_rate_of(64, "DEF") == "low" and work_rate_of(65, "DEF") == "medium"


# ---------- traits: table 1.3 ----------

def holds(trait: Trait, group="DEF", foot="R", weak=3, **kw) -> bool:
    return trait in {t for t, _ in trait_margins(group, attrs(**kw), foot, weak)}


@pytest.mark.parametrize("trait,field,threshold", [
    (Trait.RAPID, "pace", 80), (Trait.QUICK_OFF_THE_MARK, "acceleration", 80), (Trait.AERIAL_THREAT, "aerial", 72),
    (Trait.ENGINE, "stamina", 82), (Trait.TOUGH_TACKLER, "defending", 75), (Trait.VISIONARY, "vision", 78),
    (Trait.DRIBBLER, "dribbling", 78),
])
def test_threshold_traits(trait, field, threshold):
    assert holds(trait, **{field: threshold})
    assert not holds(trait, **{field: threshold - 1})


def test_long_range_needs_a_midfielder():
    assert holds(Trait.LONG_RANGE, group="MID", finishing=70)
    assert not holds(Trait.LONG_RANGE, group="MID", finishing=69)
    assert not holds(Trait.LONG_RANGE, group="FWD", finishing=90)


def test_press_resistant_needs_both_numbers():
    assert holds(Trait.PRESS_RESISTANT, dribbling=72, passing=65)
    assert not holds(Trait.PRESS_RESISTANT, dribbling=71, passing=65)
    assert not holds(Trait.PRESS_RESISTANT, dribbling=72, passing=64)


def test_two_footed_by_foot_or_weak_foot():
    assert holds(Trait.TWO_FOOTED, foot="both", weak=5)
    assert holds(Trait.TWO_FOOTED, foot="R", weak=5)
    assert not holds(Trait.TWO_FOOTED, foot="R", weak=4)


def test_set_piece_taker_is_never_a_threshold_trait():
    assert Trait.SET_PIECE_TAKER not in {t for t, _ in trait_margins("MID", attrs(passing=99, vision=99), "R", 3)}


def test_at_most_two_traits_largest_margin_first():
    a = attrs(pace=99, acceleration=90, aerial=75, stamina=85, defending=76)
    assert traits_of("DEF", a, "R", 3, taker=False) == [Trait.RAPID, Trait.QUICK_OFF_THE_MARK]
    ranked = [t for t, _ in sorted(trait_margins("DEF", a, "R", 3), key=lambda tm: -tm[1])]
    assert ranked[:2] == [Trait.RAPID, Trait.QUICK_OFF_THE_MARK]


def test_ties_break_in_table_order():
    a = attrs(pace=85, acceleration=85, aerial=77)  # margins 5, 5, 5
    assert traits_of("DEF", a, "R", 3, taker=False) == [Trait.RAPID, Trait.QUICK_OFF_THE_MARK]


def test_the_taker_keeps_the_trait_and_one_more_slot():
    a = attrs(pace=99, acceleration=90)
    assert traits_of("MID", a, "R", 3, taker=True) == [Trait.SET_PIECE_TAKER, Trait.RAPID]
    assert traits_of("MID", attrs(), "R", 3, taker=True) == [Trait.SET_PIECE_TAKER]
    assert traits_of("MID", attrs(), "R", 3, taker=False) == []


def test_two_footed_ranks_with_the_boolean_margin():
    a = attrs(pace=80 + BOOL_MARGIN + 1)
    assert traits_of("DEF", a, "both", 5, taker=False)[0] is Trait.RAPID
    a = attrs(pace=80 + BOOL_MARGIN - 1, acceleration=80 + BOOL_MARGIN - 1)
    assert traits_of("DEF", a, "both", 5, taker=False)[0] is Trait.TWO_FOOTED


def test_team_rules_one_taker_one_captain(runs):
    for _, meta in runs.values():
        for t in meta.teams.values():
            takers = [p for p in t.players if Trait.SET_PIECE_TAKER in p.traits]
            assert len(takers) == 1 and takers[0].group != "GK"
            assert takers[0].attrs.passing + takers[0].attrs.vision == max(
                p.attrs.passing + p.attrs.vision for p in t.players if p.group != "GK")
            captains = [p for p in t.players if p.captain]
            assert len(captains) == 1 and captains[0].group in ("DEF", "MID")
            assert captains[0].age + captains[0].attrs.stamina / 10 == max(
                p.age + p.attrs.stamina / 10 for p in t.players if p.group in ("DEF", "MID"))


def test_every_player_has_a_role_and_at_most_two_traits(runs):
    for _, meta in runs.values():
        for t in meta.teams.values():
            for p in t.players:
                assert p.role is not None and len(p.traits) <= 2 and len(set(p.traits)) == len(p.traits)


def test_traits_follow_the_rules_on_real_players(runs):
    for _, meta in runs.values():
        for t in meta.teams.values():
            for p in t.players:
                allowed = {tr for tr, _ in trait_margins(p.group, p.attrs, p.foot, p.weak_foot)} | {Trait.SET_PIECE_TAKER}
                assert set(p.traits) <= allowed
                # nothing with a larger margin was left out
                held = dict(trait_margins(p.group, p.attrs, p.foot, p.weak_foot))
                kept = [held[tr] for tr in p.traits if tr in held]
                left = [m for tr, m in held.items() if tr not in p.traits]
                room = 2 - (Trait.SET_PIECE_TAKER in p.traits)
                if left and len(kept) == room:
                    assert max(left) <= min(kept)
