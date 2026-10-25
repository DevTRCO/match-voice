"""The density report (docs/PLAN-DATA.md phase 3): metrics on synthetic messages, the 'before' column, the three spans, zero spend."""
import hashlib
import json
from pathlib import Path

import orjson
import pytest

from matchvoice.commentary.analyst import KEYS
from matchvoice.config import ROOT
from matchvoice.evaluation import density as dn
from matchvoice.pipeline.library import Library

LIB = Library()


def say(ch, m, s, e, text, kind="touch", t=None, src="template"):
    return {"k": "say", "t": s if t is None else t, "ch": ch, "m": m, "kind": kind, "voice": "pbp", "text": text, "s": s, "e": e, "cut": 0, "src": src}


def voice(ch, m, s, e, **kw):
    return {"k": "voice", "t": s, "ch": ch, "m": m, "s": s, "e": e, **kw}


# ---------- which lines were spoken ----------
def test_a_line_is_spoken_when_say_has_a_slot_or_a_voice_message_gives_one_and_not_when_skipped():
    msgs = [say(0, 1, 1.0, 2.5, "Voiced at once."),
            say(0, 2, 3.0, 3.0, "Captioned first."), voice(0, 2, 5.0, 6.0),
            say(0, 3, 7.0, 7.0, "Never spoken."), voice(0, 3, 8.0, 8.0, skip=1),
            say(0, 4, 9.0, 9.0, "Captioned, cut."), voice(0, 4, 9.5, 10.0, cut=1),
            say(0, 5, 11.0, 11.0, "No voice message at all.")]
    segs, say_by, voice_by = dn.segments(msgs)
    assert [(x.m, x.s, x.e) for x in segs] == [(1, 1.0, 2.5), (2, 5.0, 6.0), (4, 9.5, 10.0)]
    assert set(say_by) == {(0, i) for i in range(1, 6)} and (0, 3) in voice_by


def test_a_recorded_line_that_was_cut_ends_where_it_was_cut():
    msgs = [say(1, 7, 0.0, 4.0, "Long line"), {**say(1, 7, 0.0, 2.0, "Long line"), "cut": 1}]
    segs, _, _ = dn.segments(msgs)
    assert [(x.s, x.e) for x in segs] == [(0.0, 2.0)]


# ---------- the ten metrics ----------
class FakeNames:
    def count(self, text: str) -> int:
        return text.lower().count("ibsen")


def test_the_ten_metrics_on_a_hand_built_minute():
    lines = [  # (start, text)
        (0.0, "Ibsen."), (2.0, "Ibsen goes long to Tavares and he reaches it."), (6.0, "On it goes."), (12.0, "Good ball."),
        (20.0, "A very long sentence about how the whole match has settled down into a pattern of patient play."), (40.0, "Ibsen again.")]
    msgs = []
    for i, (s, text) in enumerate(lines):
        e = s + len(text) / 12.5 + 0.3
        msgs.append(say(0, 1_000_000 + 8 * i, s, e, text, kind="shot_goal" if i == 1 else "touch"))  # fast ids: not skeleton captions
    msgs.append(say(0, 99, 50.0, 50.0, "Skeleton line.", kind="corner", t=50.0))
    msgs.append(voice(0, 99, 52.0, 52.0, skip=1))
    msgs.append(say(0, 98, 55.0, 55.0, "Skeleton line two.", kind="corner", t=55.0))
    segs, say_by, voice_by = dn.segments(msgs)
    r = dn.channel_metrics(segs, say_by, voice_by, 0, 0.0, 60.0, FakeNames())
    assert r["segments"] == 6 and r["segments_per_min"] == pytest.approx(6.0)
    words = [len(t.split()) for _, t in lines]
    assert r["words_per_min"] == pytest.approx(sum(words))
    spoken = sum(len(t) / 12.5 + 0.3 for _, t in lines)
    assert r["coverage"] == pytest.approx(spoken / 60)
    ends = [s + len(t) / 12.5 + 0.3 for s, t in lines]
    gaps = [b[0] - e for b, e in zip(lines[1:], ends)]
    assert r["gaps_over_3s"] == pytest.approx(sum(g > 3 for g in gaps) / len(gaps))
    assert r["short_share"] == pytest.approx(sum(w <= 5 for w in words) / 6)
    assert r["long_share"] == pytest.approx(sum(w >= 12 for w in words) / 6)
    assert r["named_share"] == pytest.approx(3 / 6) and r["names_per_100"] == pytest.approx(100 * 3 / sum(words))
    assert r["skip_share"] == pytest.approx(0.5) and r["captions"] == 2 and r["skipped"] == 1
    # the words in the 30 s after the goal call (it starts at 2.0) against the whole minute
    in_goal = sum(w for (s, _), w in zip(lines, words) if 2.0 <= s < 32.0)
    assert r["after_goal"] == pytest.approx(in_goal / 0.5 / r["words_per_min"] - 1)


def test_a_channel_that_says_nothing_has_empty_ratios_not_a_crash():
    r = dn.channel_metrics([], {}, {}, 0, 0.0, 30.0, FakeNames())
    assert r["segments_per_min"] == 0 and r["coverage"] == 0 and r["gaps_over_3s"] is None and r["short_share"] is None and r["names_per_100"] is None


def test_the_names_counter_finds_surnames_not_parts_of_words():
    n = dn.Names(LIB.bundle("comeback-135"))
    assert n.count("Ibsen cuts it out, Rasmussen looks up.") == 2 and n.count("The Ibsenians sing.") == 0 and n.count("No names here.") == 0
    assert n.count("Abaras Tor") == 1 and n.count("Ibsens Tor") == 1  # a German genitive still names the player


# ---------- gates ----------
def test_the_gate_table_is_the_plan_s():
    assert dn.GATES["segments_per_min"][1:] == (16, 16, 12) and dn.GATES["coverage"][1:] == (0.75, 0.70, 0.55)
    assert dn.GATES["words_per_min"][1:] == (75, 75, 60) and dn.GATES["gaps_over_3s"][1:] == (0.12, 0.12, 0.20)
    assert dn.GATES["short_share"][1:3] == (0.40, 0.70) and dn.GATES["long_share"][1:3] == (0.05, 0.20)
    assert dn.GATES["named_share"][1:3] == (0.30, 0.55) and dn.GATES["names_per_100"][1:3] == (6.0, 14.0)
    assert dn.GATES["skip_share"][1:] == (0.35, 0.35, 0.35) and dn.GATES["after_goal"][1:] == (None, 0.0, 0.0)
    assert dn.holds("segments_per_min", 16, "insert") and not dn.holds("segments_per_min", 15.9, "windows") and dn.holds("segments_per_min", 12, "matches")
    assert dn.holds("short_share", 0.4, "windows") and not dn.holds("short_share", 0.71, "matches") and not dn.holds("long_share", 0.04, "insert")
    assert dn.holds("after_goal", None, "windows") is None and dn.holds("after_goal", 0.0, "windows") is False and dn.holds("after_goal", 0.01, "matches")
    assert dn.holds("after_goal", 5.0, "insert") is None  # not gated on the insert
    assert dn.EN_CHANNELS == [0, 1] and [KEYS[c] for c in dn.EN_CHANNELS] == ["en/beginner", "en/expert"]


def test_the_insert_is_gated_on_its_worst_channel_and_the_others_on_the_median():
    def channels(vals):
        base = {k: 0.5 for k in dn.GATES}
        return {ch: {**base, "segments_per_min": v} for ch, v in enumerate(vals)}
    one = channels([20, 20, 20, 20, 20, 15])
    assert dn.summarise([one], "insert")["segments_per_min"]["gated"] == 15
    assert dn.summarise([one], "insert")["segments_per_min"]["holds"] is False
    assert dn.summarise([one, channels([18] * 6), channels([17] * 6)], "windows")["segments_per_min"]["gated"] == 18
    assert dn.summarise([one], "matches")["segments_per_min"]["worst_channel"] == 15
    rng = dn.summarise([channels([20] * 6)], "insert")["short_share"]
    assert rng["gated"] == 0.5 and rng["holds"] is True


# ---------- the before column and the three spans ----------
def test_the_recorded_insert_reproduces_the_plan_s_numbers():
    rec = dn.measure_recorded_insert()
    for ch, r in rec.items():
        assert r["segments"] == 4 and r["segments_per_min"] == pytest.approx(11.43, abs=0.01)  # DATA-MODEL 0: 11.4 per minute
        assert 0.76 <= r["coverage"] <= 0.82  # 76 to 81 percent of the 21 s window
        assert r["gaps_over_3s"] == 0 and r["skip_share"] == 0


def test_the_windows_are_the_same_every_time_and_pick_skeleton_moments_only():
    a, b = dn.windows_of(LIB), dn.windows_of(LIB)
    assert a == b and len(a) == 20
    assert [m.split("-")[1] for m, _ in a] == [str(s) for s in range(1001, 1021)]
    assert {m.split("-")[0] for m, _ in a} <= {"comeback", "red_card", "unlucky"} and len({m.split("-")[0] for m, _ in a}) == 3
    assert all(0 < w["until"] - w["start"] <= 60.0 for _, w in a)


@pytest.fixture(scope="module")
def report():
    cache = ROOT / "data" / "cache" / "analyst"
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in cache.iterdir()} if cache.exists() else {}
    res = dn.report(LIB)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in cache.iterdir()} if cache.exists() else {}
    return res, before, after


def test_the_report_makes_no_call_and_leaves_the_answer_cache_alone(report):
    res, before, after = report
    assert res["model_calls"] == 0 and res["elevenlabs_credits"] == 0 and before == after


def test_the_report_has_the_three_spans_and_every_metric(report):
    res, _, _ = report
    assert set(res["summary"]) == {"insert", "windows", "matches"} and len(res["windows"]) == 20 and res["matches"] == list(dn.FULL_MATCHES)
    for span in dn.SPANS:
        assert set(res["summary"][span]) == set(dn.GATES)
    assert len(res["insert"]) == 6 and len(res["per_window"]) == 20 and len(res["per_match"]) == 3
    # the dense voice is far denser than the recorded insert it replaces (11.4 segments per minute, 4 lines)
    assert res["summary"]["insert"]["segments_per_min"]["gated"] > 14 and res["recorded_insert"]["segments_per_min"]["median_channel"] == pytest.approx(11.43, abs=0.01)


def test_the_gates_that_hold_after_the_review_fixes_keep_holding_and_the_ones_that_fail_are_the_ones_the_report_names(report):
    """The honest state of phase 3 (docs/DENSITY.md): a gate that is claimed green must stay green, a gate that fails must be one the report admits to."""
    res, _, _ = report

    def failing(summary: dict) -> set[str]:
        return {m for m, r in summary.items() if r["holds"] is False}

    composition = {"short_share", "named_share", "names_per_100"}  # names and verbs are the volume now: the position readouts that kept these green are gone
    assert failing(res["summary"]["matches"]) == composition
    # dossier stories (sim/dossier.py) fill quiet spells with one longer sentence where short fragments were: in the 60 s windows that
    # costs a quarter of a segment a minute (16.07 to 15.82, the gate is 16) and buys speech coverage (79.0 to 80.5 percent)
    assert failing(res["summary"]["windows"]) == {"named_share", "names_per_100", "segments_per_min"}
    assert failing(res["summary"]["insert"]) == composition | {"long_share"}  # seven segments in 21 s; the analysis template of de/beginner has 9 words
    assert failing(res["insert_stand_in"]) == composition | {"long_share"}
    assert failing(res["matches_stand_in"]) == composition
    summary = res["summary"]
    assert summary["windows"]["segments_per_min"]["gated"] >= 15.7  # was 14.4, then 16.07 before the dossier stories (see above)
    assert summary["insert"]["coverage"]["worst_channel"] >= 0.75 and summary["insert"]["skip_share"]["worst_channel"] <= 0.35  # was 69% and 50%
    assert 0.05 <= summary["matches"]["long_share"]["gated"] <= 0.20 and 0.05 <= summary["windows"]["long_share"]["gated"] <= 0.20  # was 1% and 10%
    assert summary["matches"]["skip_share"]["worst_channel"] <= 0.35
    assert summary["matches"]["after_goal"]["gated"] > 0 and summary["windows"]["after_goal"]["gated"] > 0  # a goal speeds the commentary up
    text = dn.render(res)
    assert "Not met, and why" in text and "Phase 3 review fixes, round 3" in text and "dry run" in text


def test_the_report_is_json_and_markdown_and_the_command_writes_both(report, tmp_path, monkeypatch):
    res, _, _ = report
    text = dn.render(res)
    assert text.startswith("# Density report") and "Median of 20 guided windows" in text and "Before: the insert as it is recorded" in text
    assert "—" not in text and "–" not in text
    monkeypatch.setattr(dn, "report", lambda fast=True: res)
    monkeypatch.setattr("sys.argv", ["density", "--out", str(tmp_path / "d.json"), "--report", str(tmp_path / "D.md")])
    dn.main()
    assert orjson.loads((tmp_path / "d.json").read_bytes())["model_calls"] == 0 and (tmp_path / "D.md").read_text() == text


def test_a_run_is_deterministic():
    a = dn.measure_insert(LIB)
    b = dn.measure_insert(LIB)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_the_stand_in_analyst_answers_as_the_recorded_insert_did():
    plain = dn.measure_insert(LIB)
    stand = dn.measure_insert(LIB, stand_in=True)
    assert all(stand[ch]["skip_share"] == 0 for ch in stand)  # an analyst line that arrives is spoken
    assert all(stand[ch]["coverage"] >= plain[ch]["coverage"] - 0.01 for ch in stand)
