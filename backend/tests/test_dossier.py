from matchvoice.pipeline.demo import story_insert
from matchvoice.pipeline.library import Library
from matchvoice.sim.dossier import dossier_of

LIB = Library()


def test_the_dossier_is_fixed_by_the_match_and_names_nobody_from_the_squads_by_mistake():
    meta = LIB.bundle("comeback-135").meta
    a, b = dossier_of(meta), dossier_of(meta)
    assert a.stories == b.stories and len({s.id for s in a.stories}) == len(a.stories)
    surnames = {p.name.split()[-1] for t in meta.teams.values() for p in t.players}
    for s in a.stories:
        if s.kind == "coach":
            assert s.data["coach_surname"] not in surnames  # the verifier would read it as a player who is not in the moment
        if s.kind == "former_club":
            assert s.data["club"] not in {t.name for t in meta.teams.values()}
        if s.kind == "milestone":
            assert s.data["n"] <= 99  # said in words


def test_a_comeback_side_has_its_comeback_story():
    meta = LIB.bundle("comeback-135").meta
    st = [s for s in dossier_of(meta).stories if s.kind == "comebacks" and s.side == "H"]
    assert st and st[0].data["n"] >= 1


def test_the_story_insert_tells_the_comeback_story_before_the_equaliser():
    d = story_insert(LIB)
    (a1, b1), (a2, b2) = d["parts"]
    assert a1 < d["story_t"] < b1 < a2 < d["goal_t"] < b2
    # 44 s of parts (45 s as heard, with the cut): part 1 holds the co-commentator's pattern set-up and the story (2026-10-26), part 2
    # the call, the co line that pays the set-up off and the score, with a breath before each of the last two
    assert d["length"] == round((b1 - a1) + (b2 - a2)) and d["length"] <= 44
