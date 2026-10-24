"""Director: decides what is said, when, and in which words, under a speech-time budget.

One voice per channel (a language and style). The director keeps silence when nothing
matters, lets the highest-priority moment speak first, interrupts for goals and red
cards, and picks the longest wording that fits the time it has. Every decision, spoken
or dropped, is recorded for the log. Time-to-live and speech time are viewer seconds, so a fast
replay (speed > 1) keeps the same balance between play-by-play and analysis.

`ChannelDirector` is the stepwise form: push moments as they become known, advance the clock,
read what started or was cut. `schedule` runs it over a complete list of moments in one go.

Caption time and speech time are separate in the live form (`captions_first`): a moment is captioned the instant it
arrives, whatever the voice is doing, and only the voice queues. A line that waits for the voice too long
(`voice_wait_s`, viewer seconds after its caption) or outlives its time-to-live is skipped: shown, never spoken.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Callable

from .lang import est_seconds
from .moments import Moment

INF = float("inf")

# The dense layers (docs/DATA-MODEL.md 7.1 and 7.2), applied only to moments of layer fast or context and only when `dense` is on
FAST_GAP_S = 1.2  # viewer seconds between the starts of two fast lines on a channel
CONTEXT_PLAY_S = 12.0  # one context line per this many viewer seconds while the ball is in play ...
CONTEXT_DEAD_S = 7.0  # ... and per this many in a dead ball
CONTEXT_PER_WINDOW = 3  # at most this many context lines in one dead-ball window
ARRIVAL_SLACK_S = 0.2  # a pass fragment is about the kick: it should be finished by the time the ball arrives (plus this: a first-time pass follows within about 0.2 s and is the news then)
SILENT_LAYERS = ("fast", "context")  # captioned when the voice takes them, never at arrival: a fragment replaced before it is voiced is not a skip


@dataclass
class Spoken:
    moment_id: int
    kind: str
    voice: str
    start: float  # match seconds
    end: float
    text: str
    cut: bool = False  # interrupted by something more important


@dataclass
class Dropped:
    moment_id: int
    kind: str
    reason: str  # low_priority | stale


class ChannelDirector:
    """Schedules one channel. `speed` is match seconds per wall second (1 = real time).

    It only knows the moments pushed so far, so a live run decides without foresight while a
    run that pushes everything up front can pick wordings that fit before the next big moment.
    """

    def __init__(self, variants_of: Callable[[Moment], list[str]], lang: str, speed: float = 1.0,
                 min_priority: int = 25, interrupt_min: int = 90, interrupt_margin: int = 20,
                 max_line_s: float = 25.0, captions_first: bool = False,
                 voice_wait_s: Callable[[Moment], float] | float = INF,
                 has_model_line: Callable[[Moment], bool] | None = None, dense: bool = False,
                 short_kinds: frozenset[str] = frozenset()):
        self.variants_of, self.lang, self.speed = variants_of, lang, speed
        self.dense, self.short_kinds = dense, short_kinds  # dense: the fast and context rules; short_kinds: skeleton kinds that take their shortest wording
        self._fast_at = -INF  # earliest start of the next fast line
        self._ctx_last = -INF  # start of the last context line
        self._ctx_window: dict[int, int] = {}  # dead-ball window -> context lines started in it
        self.min_priority, self.interrupt_min = min_priority, interrupt_min
        self.interrupt_margin, self.max_line_s = interrupt_margin, max_line_s
        self.captions_first = captions_first
        self._has_model_line = has_model_line or (lambda _m: False)  # the last wording of the moment is the model's, not a template slot
        self._voice_wait = voice_wait_s if callable(voice_wait_s) else (lambda _m: voice_wait_s)
        self._text: dict[int, str] = {}  # captions_first: wording fixed at caption time, the voice reads the same text
        self._arrived: dict[int, float] = {}  # captions_first: when each waiting moment was captioned
        self.out: list[Spoken] = []
        self.dropped: list[Dropped] = []
        # ("start" | "cut", line), drained by the caller. captions_first adds ("caption", line) when a moment is
        # shown (start == end == its time) and ("skip", line) when the voice gave up on it
        self.notices: list[tuple[str, Spoken]] = []
        self._arrivals: list[Moment] = []
        self._i = 0
        self._queue: list[Moment] = []
        self._cur: tuple[Moment, float, float, str] | None = None
        self._last_said: dict[str, str] = {}
        self._last_slot: dict[str, int] = {}  # kind -> position of the wording chosen last
        self._turn: dict[tuple[str, str], int] = {}  # (kind, wording without the names) -> when a fast fragment last used it
        self._count = 0
        self._now = 0.0

    @property
    def idle(self) -> bool:
        return self._cur is None and not self._queue and self._i >= len(self._arrivals)

    def push(self, m: Moment) -> None:
        """Make a moment known. It is acted on once the clock reaches its `ready_t`."""
        bisect.insort(self._arrivals, m, lo=self._i, key=lambda x: (x.ready_t, -x.priority))

    def drain(self) -> list[tuple[str, Spoken]]:
        out, self.notices = self.notices, []
        return out

    def _speech(self, text: str) -> float:
        return est_seconds(text, self.lang) * self.speed

    def _silent(self, m: Moment) -> bool:
        return self.dense and m.layer in SILENT_LAYERS

    def _expire(self, t: float) -> None:
        for m in list(self._queue):
            if t > m.t + m.ttl * self.speed or self._waited_too_long(m, t):  # worth saying for ttl viewer seconds
                self._queue.remove(m)
                self.dropped.append(Dropped(m.id, m.kind, "stale"))
                self._skip(m, t)

    def _gap(self, m: Moment) -> float:
        return (CONTEXT_DEAD_S if m.params.get("dead") else CONTEXT_PLAY_S) * self.speed

    def _can_start(self, m: Moment, t: float) -> bool:
        """The pace rules of the dense layers: fast lines are spaced, context lines are capped and wait for a quiet moment."""
        if not self.dense:
            return True
        if m.layer == "fast":
            return t >= self._fast_at - 1e-9
        if m.layer == "context":
            if t < self._ctx_last + self._gap(m) - 1e-9:
                return False
            if m.params.get("dead"):
                return self._ctx_window.get(m.params.get("window"), 0) < CONTEXT_PER_WINDOW
            return not any(q.layer == "fast" for q in self._queue)  # in play only when no fast fragment is waiting
        return True

    def _wake(self) -> float:
        """The next time a waiting moment becomes startable by the clock alone (INF: only an arrival or a start can change that)."""
        if not self.dense:
            return INF
        wakes = [self._fast_at for m in self._queue if m.layer == "fast" and self._fast_at > self._now]
        wakes += [self._ctx_last + self._gap(m) for m in self._queue if m.layer == "context" and self._ctx_last + self._gap(m) > self._now]
        return min(wakes, default=INF)

    def _pick(self, t: float) -> Moment | None:
        self._expire(t)
        return max((m for m in self._queue if self._can_start(m, t)), key=lambda m: (m.priority, -m.t), default=None)

    def _waited_too_long(self, m: Moment, t: float) -> bool:
        """The voice must not start a captioned line more than `voice_wait_s` viewer seconds after its caption.
        Moments that may interrupt (goals, red cards, whistles) are exempt."""
        if not self.captions_first or m.priority >= self.interrupt_min:
            return False
        return t > self._arrived.get(m.id, m.t) + self._voice_wait(m) * self.speed

    def _skip(self, m: Moment, t: float) -> None:
        text = self._text.pop(m.id, None)
        self._arrived.pop(m.id, None)
        if self.captions_first and text is not None:
            self.notices.append(("skip", Spoken(m.id, m.kind, m.voice, t, t, text)))

    def _arrive(self, m: Moment) -> None:
        if m.priority < self.min_priority:
            self.dropped.append(Dropped(m.id, m.kind, "low_priority"))
        elif self.captions_first and self._now > m.t + m.ttl * self.speed:
            self.dropped.append(Dropped(m.id, m.kind, "stale"))  # too late to be worth even a caption
        else:
            if self.dense and m.layer == "fast":  # a newer fragment replaces an older one still waiting: no queue of fragments
                for q in [q for q in self._queue if q.layer == "fast" and q.priority <= m.priority]:
                    self._queue.remove(q)
                    self._arrived.pop(q.id, None)
                    self.dropped.append(Dropped(q.id, q.kind, "replaced"))
            self._queue.append(m)
            if self._silent(m):
                self._arrived[m.id] = self._now  # no caption yet: it is captioned when the voice takes it
            elif self.captions_first:
                text = self._choose(m, lookahead=False)  # wording is fixed before the voice's turn is known
                self._text[m.id], self._arrived[m.id] = text, self._now
                self.notices.append(("caption", Spoken(m.id, m.kind, m.voice, self._now, self._now, text)))

    @staticmethod
    def _shape(m: Moment, text: str) -> str:
        """A wording with the players' names taken out, so "Lemaire to Rahimi." and "Ibsen to Tavares." are one wording."""
        for key in ("player", "target", "kicker", "defender", "winner", "presser", "runner", "taker", "attacker", "receiver", "keeper"):
            if isinstance(m.params.get(key), str):
                text = text.replace(m.params[key], "_")
        return text

    def _choose(self, m: Moment, lookahead: bool = True) -> str:
        """The preferred fresh wording that fits the time before the next more important moment we know of.

        `variants_of` lists the wordings in order of preference, least first: templates short to long, and a model line
        last, which wins whatever its length as long as it fits. Only when it does not fit does a template take over."""
        texts = list(self.variants_of(m))
        if m.kind in self.short_kinds or (self.dense and m.layer == "context" and not m.params.get("long")):
            texts = texts[:1]  # ball in play: the shortest wording, the longer ones are for dead balls
        limit = next((a.ready_t for a in self._arrivals[self._i:] if a.priority > m.priority), INF) if lookahead else INF
        if self.dense and m.layer == "fast" and "arr" in m.params:  # the shortest wording that ends before the ball lands, else the shortest
            limit = min(limit, m.params["arr"] + ARRIVAL_SLACK_S * self.speed)
        budget = min(max(limit - self._now, 0.0), self.max_line_s * self.speed)
        fitting = [x for x in texts if self._speech(x) <= budget] or texts[:1]
        fresh = [x for x in fitting if x != self._last_said.get(m.kind)] or [x for x in texts if x != self._last_said.get(m.kind)]
        model = len(texts) - 1 if texts and self._has_model_line(m) else -1
        if self.captions_first:  # live: two moments of one kind in a row also avoid the same template wording (same slot in the list), not only the same text.
            last = self._last_slot.get(m.kind)  # Template wordings only: the model line is never filtered by slot.
            if not (self.dense and m.layer == "context"):  # a dead ball takes the long wording every time it has one
                fresh = [x for x in fresh if texts.index(x) == model or texts.index(x) != last] or fresh
        text = (fresh or fitting)[-1]
        if self.dense and m.layer == "fast":
            # fragments take turns: the wording of its kind used longest ago (the longest on a tie), so one wording is not said again and again;
            # the names do not count ("Lemaire to Rahimi." and "Ibsen to Tavares." are one wording)
            text = min(fresh or fitting, key=lambda x: (self._turn.get((m.kind, self._shape(m, x)), -1), -len(x)))
            self._count += 1
            self._turn[(m.kind, self._shape(m, text))] = self._count
        self._last_said[m.kind] = text
        slot = texts.index(text)
        if slot != model:  # a model line is no template slot: the next moment of this kind keeps the slot of the last template
            self._last_slot[m.kind] = slot
        return text

    def _start(self, m: Moment) -> None:
        text = self._text.pop(m.id) if m.id in self._text else self._choose(m, lookahead=not self.captions_first)
        self._arrived.pop(m.id, None)
        if self.dense and m.layer == "fast":
            self._fast_at = self._now + FAST_GAP_S * self.speed
        elif self.dense and m.layer == "context":
            self._ctx_last = self._now
            if m.params.get("dead"):
                w = m.params.get("window")
                self._ctx_window[w] = self._ctx_window.get(w, 0) + 1
        self._cur = (m, self._now, self._now + self._speech(text), text)
        self.notices.append(("start", Spoken(m.id, m.kind, m.voice, self._now, self._cur[2], text)))

    def advance(self, until: float) -> None:
        """Run the channel forward to match time `until`, acting only on what is known."""
        self._advance(until)
        if self.dense and until < INF:  # a fast or context line nobody can start any more is stale: the channel may go idle
            for m in [m for m in self._queue if m.layer in SILENT_LAYERS and until > m.t + m.ttl * self.speed]:
                self._queue.remove(m)
                self._arrived.pop(m.id, None)
                self.dropped.append(Dropped(m.id, m.kind, "stale"))

    def _advance(self, until: float) -> None:
        while True:
            next_arr = self._arrivals[self._i].ready_t if self._i < len(self._arrivals) else INF
            if self._cur is None:
                m = self._pick(self._now)
                if m is not None:
                    self._queue.remove(m)
                    self._start(m)
                    continue
                wake = self._wake()  # a waiting fast or context line that only the clock holds back
                if min(next_arr, wake) > until or min(next_arr, wake) == INF:
                    break
                if wake < next_arr:
                    self._now = max(self._now, wake)
                    continue
                self._now = max(self._now, next_arr)
                self._arrive(self._arrivals[self._i])
                self._i += 1
                continue

            m, start, end, text = self._cur
            if end <= next_arr:
                if end > until:
                    break
                self.out.append(Spoken(m.id, m.kind, m.voice, start, end, text))
                self._now, self._cur = end, None
                continue
            if next_arr > until:
                break
            a = self._arrivals[self._i]
            self._i += 1
            self._now = max(self._now, a.ready_t)
            self._arrive(a)
            if (a.priority >= self.interrupt_min and m.priority < self.interrupt_min
                    and a.priority >= m.priority + self.interrupt_margin):
                cut = Spoken(m.id, m.kind, m.voice, start, self._now, text, cut=True)
                self.out.append(cut)
                self.notices.append(("cut", cut))
                self._cur = None

    def close(self) -> tuple[list[Spoken], list[Dropped]]:
        """Everything still waiting is stale. Call after the last advance."""
        for m in self._queue:
            self.dropped.append(Dropped(m.id, m.kind, "stale"))
            self._skip(m, self._now)
        self._queue = []
        return self.out, self.dropped


def schedule(
    moments: list[Moment],
    variants_of: Callable[[Moment], list[str]],
    lang: str,
    speed: float = 1.0,
    min_priority: int = 25,
    interrupt_min: int = 90,
    interrupt_margin: int = 20,
    max_line_s: float = 25.0,
) -> tuple[list[Spoken], list[Dropped]]:
    """Schedule one channel over a complete list of moments."""
    d = ChannelDirector(variants_of, lang, speed, min_priority, interrupt_min, interrupt_margin, max_line_s)
    for m in moments:
        d.push(m)
    d.advance(INF)
    return d.close()
