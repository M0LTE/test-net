#!/usr/bin/env python3
"""Synthetic background chat traffic for the test net.

Connects four "personas" via four user-node stations' BPQ Telnet
consoles, drops each one into the Durham hub's chat application
(`C QD0HUB-2`), and runs scripted topic threads at slow cadence.

Per-message delay 20-90 s, 60-300 s of quiet between threads. The
intent is *presence* — a low background of RF activity on the town
channels and the backbone, not a flood.

Stdlib only.
"""
from __future__ import annotations

import os
import random
import socket
import sys
import threading
import time
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------

@dataclass
class Persona:
    nick: str          # the chat name the bot uses
    host: str          # the BPQ node container to telnet into
    port: int          # always 8010 (internal Telnet port)
    user: str = "user"
    password: str = "pass"


PERSONAS = [
    Persona("m0abc", host="QA0ABN", port=8010),   # Aberdeen user
    Persona("g4xyz", host="QE0EXS", port=8010),   # Exeter user
    Persona("2e1pq", host="QC0CAS", port=8010),   # Cambridge user
    Persona("m7hij", host="QD0DUR", port=8010),   # Durham user (close to chat host)
]

# ---------------------------------------------------------------------------
# Conversation material — short topic threads. The director picks one at
# random, walks through it message-by-message at slow cadence, then sits
# quiet for a while before picking another. Speakers in each thread are
# explicit so the dialogue is coherent.
# ---------------------------------------------------------------------------

THREADS: list[list[tuple[str, str]]] = [
    [
        ("m0abc", "evening all"),
        ("g4xyz", "evening tom, anything on 2m up there?"),
        ("m0abc", "dead as a doornail. tried calling on 145.500 simplex earlier, nothing"),
        ("g4xyz", "same here. ridge's been sitting south of us all day"),
        ("2e1pq", "evening gents, just got the kettle on"),
        ("m0abc", "kettle is the only thing working on 2m today"),
    ],
    [
        ("g4xyz", "anyone running the new linbpq build yet"),
        ("m7hij", "i pulled it last night. the prefix routing change seems to behave"),
        ("g4xyz", "yeah that's the bit i was waiting for. fixes my double-pass nodes table issue"),
        ("m0abc", "i'll update at the weekend, don't want to take the bbs down mid-week"),
        ("m7hij", "fair. it's been steady for me, ~14 hours uptime"),
    ],
    [
        ("2e1pq", "putting up a new efhw this weekend if the wind drops"),
        ("m7hij", "40m?"),
        ("2e1pq", "yeah, 40 through 10. silver-plated 20 awg"),
        ("m7hij", "should be quiet. let me know how it tunes"),
        ("2e1pq", "will do. last one was noisy as anything, RF in the shack"),
    ],
    [
        ("g4xyz", "anyone heard from steve recently"),
        ("m0abc", "not for a week or so, think he's at the rally"),
        ("g4xyz", "right, of course. is that the one at blackpool?"),
        ("m0abc", "yeah. should be back monday i think"),
    ],
    [
        ("m7hij", "the chat server seems happier today"),
        ("g4xyz", "yeah it was wedged a bit earlier wasn't it"),
        ("m7hij", "appl slot mixup apparently. tom fixed it"),
        ("m0abc", "ssh, don't tell anyone i was awake at 2am"),
    ],
    [
        ("2e1pq", "what's everyone running on hf at the moment"),
        ("m0abc", "ft-991a here, into an off-centre fed"),
        ("g4xyz", "icom 7300, fan dipole. boring but works"),
        ("m7hij", "kx3 + bnc whip out of the kitchen window. don't laugh"),
        ("2e1pq", "haha. it'll work great until it doesn't"),
    ],
    [
        ("m0abc", "did anyone work df0xx in the contest"),
        ("m7hij", "had them on 80 saturday night, just"),
        ("m0abc", "i got them sunday morning on 40, took 6 calls"),
        ("g4xyz", "didn't even hear them, my noise floor was awful all weekend"),
    ],
    [
        ("g4xyz", "anyone tried that ft8 bridge for bpq yet"),
        ("2e1pq", "no — sounds interesting though. is it just a kiss frontend?"),
        ("g4xyz", "more or less. you point it at wsjt-x's UDP output"),
        ("2e1pq", "could see that being useful for ground-wave nvis stuff"),
        ("m7hij", "or just for getting traffic in when 144 is dead. which is most evenings"),
    ],
    [
        ("m7hij", "73 all, going qrt for tea"),
        ("m0abc", "73 mike"),
        ("g4xyz", "73"),
        ("2e1pq", "73, enjoy"),
    ],
    [
        ("2e1pq", "nothing on the cluster tonight either"),
        ("m0abc", "the bands have been weird this week"),
        ("g4xyz", "k-index is up. quiet sun and a stream off the equatorial hole"),
        ("2e1pq", "you make that sound very dramatic"),
        ("g4xyz", "i was trying"),
    ],
]


# ---------------------------------------------------------------------------
# Telnet/chat session for one persona
# ---------------------------------------------------------------------------

class Session:
    def __init__(self, persona: Persona):
        self.p = persona
        self.sock: socket.socket | None = None
        self.recv_buf = b""

    def log(self, msg: str) -> None:
        print(f"[{self.p.nick}@{self.p.host}] {msg}", flush=True)

    def connect(self) -> None:
        # Resolve the BPQ container by name within the docker network.
        for attempt in range(10):
            try:
                self.sock = socket.create_connection(
                    (self.p.host, self.p.port), timeout=5
                )
                break
            except OSError as e:
                self.log(f"connect attempt {attempt + 1}: {e}; retrying")
                time.sleep(3)
        if self.sock is None:
            raise RuntimeError(f"could not connect to {self.p.host}:{self.p.port}")
        self.sock.settimeout(0.5)

    def drain(self, timeout: float = 0.5) -> bytes:
        """Pull whatever the server has sent."""
        deadline = time.monotonic() + timeout
        out = b""
        while time.monotonic() < deadline:
            try:
                self.sock.settimeout(deadline - time.monotonic())
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                out += chunk
            except (socket.timeout, TimeoutError):
                break
            except OSError:
                break
        return out

    def wait_for(self, needle: bytes, timeout: float = 15.0) -> bytes:
        """Read until needle appears in the buffer (or timeout)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.recv_buf += self.drain(timeout=0.3)
            if needle in self.recv_buf:
                idx = self.recv_buf.find(needle) + len(needle)
                got, self.recv_buf = self.recv_buf[:idx], self.recv_buf[idx:]
                return got
        raise TimeoutError(f"did not see {needle!r} (last buf: {self.recv_buf[-200:]!r})")

    def send(self, line: str) -> None:
        assert self.sock is not None
        self.sock.sendall((line + "\r\n").encode("utf-8"))

    def login_and_enter_chat(self) -> None:
        # BPQ's Telnet driver speaks plain telnet, which means an IAC
        # negotiation precedes the login prompt. We don't bother
        # responding to IAC — BPQ accepts the username regardless, but
        # the IAC bytes in our buffer can confuse needle-based reads.
        # Strategy: just give BPQ enough wall-clock time to reach each
        # state, drain liberally, and don't fight the prompt parsing.
        time.sleep(1.5)            # let IAC + "user:" arrive
        self.drain(timeout=0.5)
        self.send(self.p.user)
        time.sleep(1.5)            # let "password:" arrive
        self.drain(timeout=0.5)
        self.send(self.p.password)
        time.sleep(3.0)            # let CTEXT + prompt arrive
        self.drain(timeout=1.0)
        self.log("logged into BPQ console")

        # C QD0HUB-2 at the BPQ prompt. If the same callsign already has
        # a chat session live (e.g. we're reconnecting after a restart
        # and the previous bot didn't /EX cleanly), BPQ Chat skips the
        # "Please enter your Name" prompt and drops us straight into
        # the session. So we wait for *either* prompt indicating we're
        # in chat, then issue /N to set the nickname unconditionally.
        self.send("C QD0HUB-2")
        deadline = time.monotonic() + 120
        in_chat = False
        while time.monotonic() < deadline:
            self.recv_buf += self.drain(timeout=0.5)
            if b"Please enter your Name" in self.recv_buf:
                self.send(self.p.nick)
                time.sleep(3)
                self.drain(timeout=2)
                in_chat = True
                break
            # Reconnect-with-existing-session shows /p-style output
            # listing connected stations, never reaching a name prompt.
            if b"Station(s) connected" in self.recv_buf or b" at CHT " in self.recv_buf:
                in_chat = True
                break
        if not in_chat:
            raise TimeoutError("chat did not respond in 120 s")
        # /N sets / updates the displayed nickname so other users see,
        # e.g., "m0abc:" instead of "QA0ABN:".
        self.send(f"/N {self.p.nick}")
        time.sleep(1)
        self.drain(timeout=1)
        self.log("in chat as " + self.p.nick)

    def say(self, text: str) -> None:
        self.send(text)
        # Lightly drain so the socket buffer doesn't fill on the
        # otherwise idle inbound path.
        self.drain(timeout=0.2)

    def keepalive(self) -> None:
        self.drain(timeout=0.2)

    def close(self) -> None:
        try:
            self.send("/EX")
            time.sleep(0.5)
            self.send("BYE")
        finally:
            if self.sock:
                self.sock.close()
                self.sock = None


# ---------------------------------------------------------------------------
# Director
# ---------------------------------------------------------------------------

def director(sessions: dict[str, Session]) -> None:
    """Play threads at random with brisk cadence and short quiet gaps."""
    rng = random.Random(os.environ.get("CHATBOT_SEED") or None)

    # Pacing — overridable via env so the cadence can be tuned without
    # editing the script. Defaults are deliberately chatty.
    msg_min = float(os.environ.get("CHATBOT_MSG_MIN_S", "8"))
    msg_max = float(os.environ.get("CHATBOT_MSG_MAX_S", "30"))
    gap_min = float(os.environ.get("CHATBOT_GAP_MIN_S", "20"))
    gap_max = float(os.environ.get("CHATBOT_GAP_MAX_S", "90"))

    while True:
        thread = rng.choice(THREADS)
        print(f"\n--- starting thread ({len(thread)} lines) ---", flush=True)
        for speaker, text in thread:
            # Per-message delay before the line lands.
            time.sleep(rng.uniform(msg_min, msg_max))
            sess = sessions.get(speaker)
            if sess is None:
                continue
            print(f"[{speaker}] {text}", flush=True)
            try:
                sess.say(text)
            except OSError as e:
                print(f"[{speaker}] say failed ({e}); reconnecting", flush=True)
                try:
                    sess.close()
                except Exception:
                    pass
                try:
                    sess.connect()
                    sess.login_and_enter_chat()
                    sess.say(text)
                except Exception as e2:
                    print(f"[{speaker}] reconnect failed: {e2}", flush=True)
            # Keep other sessions alive (drain idle inbound).
            for other in sessions.values():
                if other is not sess:
                    try:
                        other.keepalive()
                    except OSError:
                        pass
        gap = rng.uniform(gap_min, gap_max)
        print(f"--- thread done; quiet for {gap:.0f}s ---", flush=True)
        # Keepalive throughout the quiet period.
        end = time.monotonic() + gap
        while time.monotonic() < end:
            for s in sessions.values():
                try:
                    s.keepalive()
                except OSError:
                    pass
            time.sleep(5)


def main() -> int:
    # Boot-stagger so the BPQ nodes have a chance to come up if we were
    # started in the same compose `up`.
    time.sleep(int(os.environ.get("CHATBOT_BOOT_DELAY", "20")))

    sessions: dict[str, Session] = {}
    for p in PERSONAS:
        s = Session(p)
        s.connect()
        s.login_and_enter_chat()
        sessions[p.nick] = s
        # Slight stagger so they don't all arrive on the same second.
        time.sleep(2)
    print(f"all {len(sessions)} personas joined chat", flush=True)

    try:
        director(sessions)
    except KeyboardInterrupt:
        pass
    finally:
        for s in sessions.values():
            try:
                s.close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
