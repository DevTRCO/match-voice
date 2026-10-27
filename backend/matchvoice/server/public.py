"""The public server's gate: browser sessions, per-session and per-IP run caps, concurrent runs, per-session voice credits.

Only a server started with MATCHVOICE_PUBLIC=1 enforces it (create_app(public=...)); local development is unchanged.

Sessions: the page and the API live on different origins, so a cookie would be third-party and blocked. GET /api/session issues
an HMAC-signed token `<id>.<day>.<sig>` (secret MATCHVOICE_SESSION_SECRET); the page keeps it in sessionStorage and sends it as
`token=` on /ws, /sse and /api/tts. A token is valid on its issue day and the next UTC day. Without a secret a public server issues
no tokens and refuses live runs (code no_session_secret); replays keep working.

Everything is counted in memory under one lock, rolling over at midnight UTC: one replica (min = max = 1) keeps the counts true,
and a restart resets them (docs/DEPLOY.md). Refusals are LiveUnavailable with the codes documented in docs/PROTOCOL.md.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from ..pipeline.runner import LiveUnavailable

SESSIONS_KEPT = 20_000  # session records kept in memory (oldest dropped first); one record is a few dozen bytes
RUN_OWNERS_KEPT = 64  # live runs whose session the voice endpoint can still check


def _day(clock: Callable[[], datetime]) -> str:
    return clock().strftime("%Y-%m-%d")


@dataclass
class _Session:
    day: str  # the UTC day its run count belongs to
    runs: int = 0
    credits: float = 0.0  # voice credits billed (or reserved) for this session's lines


@dataclass
class PublicGate:
    secret: bytes | None  # HMAC key; None: no tokens, live refused
    session_runs: int = 3  # live runs per session (0 turns it off)
    ip_runs: int = 10  # live runs per client IP per UTC day (0 turns it off)
    concurrent: int = 3  # live runs at once (0 turns it off)
    session_credits: float = 900.0  # ElevenLabs credits per session (0 turns it off): 3 voiced runs of a generated scene, about 250 each
    ip_credits: float = 1500.0  # ElevenLabs credits per client IP per UTC day (about 5 voiced runs), so new sessions do not refill the voice (0 turns it off)
    run_channels: int = 2  # channels one run may voice: the one watched plus one switch (0 turns it off)
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _sessions: OrderedDict = field(default_factory=OrderedDict, init=False, repr=False)
    _ips: dict = field(default_factory=dict, init=False, repr=False)
    _ip_credits: dict = field(default_factory=dict, init=False, repr=False)  # ip -> voice credits billed today
    _ip_day: str = field(default="", init=False, repr=False)
    _active: int = field(default=0, init=False, repr=False)
    _owners: OrderedDict = field(default_factory=OrderedDict, init=False, repr=False)  # run id -> session id
    _voiced: dict = field(default_factory=dict, init=False, repr=False)  # run id -> the channels it has voiced, in order

    @classmethod
    def from_env(cls) -> "PublicGate":
        raw = os.environ.get("MATCHVOICE_SESSION_SECRET", "")
        return cls(raw.encode() if raw else None,
                   session_runs=int(os.environ.get("MATCHVOICE_SESSION_RUNS", "3")),
                   ip_runs=int(os.environ.get("MATCHVOICE_IP_RUNS", "10")),
                   concurrent=int(os.environ.get("MATCHVOICE_LIVE_CONCURRENT", "3")),
                   session_credits=float(os.environ.get("MATCHVOICE_SESSION_CREDITS", "900")),
                   ip_credits=float(os.environ.get("MATCHVOICE_IP_CREDITS", "1500")),
                   run_channels=int(os.environ.get("MATCHVOICE_RUN_VOICE_CHANNELS", "2")))

    # ---------- tokens ----------
    def _sign(self, sid: str, day: str) -> str:
        return hmac.new(self.secret, f"{sid}.{day}".encode(), hashlib.sha256).hexdigest()[:32]

    def issue(self) -> dict:
        """A new session. Raises LiveUnavailable(no_session_secret) when the server has no secret."""
        if not self.secret:
            raise LiveUnavailable("no_session_secret", "this server issues no sessions (no session secret is configured), "
                                  "the recorded run still works")
        sid, day = secrets.token_hex(8), _day(self.clock)
        return {"token": f"{sid}.{day}.{self._sign(sid, day)}", "id": sid, "day": day}

    def verify(self, token: str | None, any_day: bool = False) -> str | None:
        """The session id of a valid token (signature right, issued today or yesterday UTC), else None. `any_day` checks the
        signature only: the voice of a run that crosses midnight is bound by the run's owner, not by the token's day."""
        if not self.secret or not token or token.count(".") != 2:
            return None
        sid, day, sig = token.split(".")
        if not hmac.compare_digest(sig, self._sign(sid, day)):
            return None
        if any_day:
            return sid
        today = self.clock()
        if day not in (today.strftime("%Y-%m-%d"), (today - timedelta(days=1)).strftime("%Y-%m-%d")):
            return None
        return sid

    def session_id(self, token: str | None) -> str:
        """The session id, or LiveUnavailable(session_required / no_session_secret)."""
        if not self.secret:
            raise LiveUnavailable("no_session_secret", "this server issues no sessions (no session secret is configured), "
                                  "the recorded run still works")
        sid = self.verify(token)
        if sid is None:
            raise LiveUnavailable("session_required", "a live run needs a valid session token: get one from /api/session")
        return sid

    # ---------- counts ----------
    def _session(self, sid: str) -> _Session:
        s = self._sessions.get(sid)
        if s is None:
            s = self._sessions[sid] = _Session(_day(self.clock))
            while len(self._sessions) > SESSIONS_KEPT:
                self._sessions.popitem(last=False)
        return s

    def _roll_ips(self) -> None:
        day = _day(self.clock)
        if day != self._ip_day:
            self._ip_day, self._ips, self._ip_credits = day, {}, {}

    def left(self, sid: str | None, ip: str | None) -> dict:
        """What a page may still do: runs left in its session and for its IP today, voice credits left in its session."""
        with self._lock:
            self._roll_ips()
            s = self._sessions.get(sid) if sid else None
            return {"session_runs_left": None if not self.session_runs else
                    (self.session_runs - (s.runs if s else 0) if sid else None),
                    "session_runs": self.session_runs or None,
                    "ip_runs_left": None if not self.ip_runs or not ip else max(0, self.ip_runs - self._ips.get(ip, 0)),
                    "session_credits_left": None if not self.session_credits or not sid else
                    max(0.0, self.session_credits - (s.credits if s else 0.0)),
                    "ip_credits_left": None if not self.ip_credits or not ip else max(0.0, self.ip_credits - self._ip_credits.get(ip, 0.0)),
                    "busy": bool(self.concurrent) and self._active >= self.concurrent}

    def check(self, sid: str, ip: str | None) -> None:
        """Refuse a live run that would pass a cap; counts nothing."""
        with self._lock:
            self._check(sid, ip)

    def _check(self, sid: str, ip: str | None) -> None:
        self._roll_ips()
        s = self._sessions.get(sid)
        if self.session_runs and s is not None and s.runs >= self.session_runs:
            raise LiveUnavailable("session_limit", f"this session has used its {self.session_runs} live runs; "
                                  "the recorded run and the runs already made can still be watched")
        if self.ip_runs and ip and self._ips.get(ip, 0) >= self.ip_runs:
            raise LiveUnavailable("ip_limit", f"{self.ip_runs} live runs from this address today; back after midnight UTC")
        if self.concurrent and self._active >= self.concurrent:
            raise LiveUnavailable("busy", f"{self.concurrent} live runs are playing right now, try again in a minute")

    def claim(self, sid: str, ip: str | None) -> Callable[[], None]:
        """Check and count one live run under the lock; returns the release for its concurrency slot (idempotent)."""
        with self._lock:
            self._check(sid, ip)
            self._session(sid).runs += 1
            if ip:
                self._ips[ip] = self._ips.get(ip, 0) + 1
            self._active += 1
        done = []

        def release() -> None:
            if not done:
                done.append(1)
                with self._lock:
                    self._active = max(0, self._active - 1)
        return release

    @property
    def active(self) -> int:
        return self._active

    # ---------- runs and voice credits ----------
    def own(self, run_id: str, sid: str) -> None:
        with self._lock:
            self._owners[run_id] = sid
            while len(self._owners) > RUN_OWNERS_KEPT:
                self._voiced.pop(self._owners.popitem(last=False)[0], None)

    def owner(self, run_id: str | None) -> str | None:
        with self._lock:
            return self._owners.get(run_id or "")

    def voice_channel(self, run_id: str, ch: int) -> bool:
        """May this run voice channel `ch`? A run voices the channel its viewer watches plus `run_channels - 1` switches; the first
        lines asked for fix them. Refusing the rest keeps one visitor from voicing every channel of a run."""
        if not self.run_channels:
            return True
        with self._lock:
            seen = self._voiced.setdefault(run_id, [])
            if ch in seen:
                return True
            if len(seen) >= self.run_channels:
                return False
            seen.append(ch)
            return True

    def reserve_credits(self, sid: str, need: float, ip: str | None = None) -> str | None:
        """Take `need` voice credits from the session and from the address's day, or name the cap that refuses them
        (`tts_session_limit` or `tts_ip_limit`; nothing taken then)."""
        if need <= 0:
            return None
        with self._lock:
            self._roll_ips()
            s = self._session(sid)
            if self.session_credits and s.credits + need > self.session_credits + 1e-9:
                return "tts_session_limit"
            if self.ip_credits and ip and self._ip_credits.get(ip, 0.0) + need > self.ip_credits + 1e-9:
                return "tts_ip_limit"
            if self.session_credits:
                s.credits += need
            if self.ip_credits and ip:
                self._ip_credits[ip] = self._ip_credits.get(ip, 0.0) + need
            return None

    def refund_credits(self, sid: str, amount: float, ip: str | None = None) -> None:
        if amount <= 0:
            return
        with self._lock:
            if self.session_credits:
                s = self._session(sid)
                s.credits = max(0.0, s.credits - amount)
            if self.ip_credits and ip and ip in self._ip_credits:  # a refund after midnight finds a new day: nothing to give back
                self._ip_credits[ip] = max(0.0, self._ip_credits[ip] - amount)
