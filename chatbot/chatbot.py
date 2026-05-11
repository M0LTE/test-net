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
        deadline = time.monotonic() + 180
        in_chat = False
        # Markers that mean we're definitely in chat (any one is enough).
        in_chat_markers = (
            b"Station(s) connected",
            b" at CHT ",
            b"[BPQChatServer",
            b"old session will be closed",
        )
        # Markers that mean the connect failed before reaching chat —
        # NETROM didn't have the route, or BPQ parsed the command as a
        # downlink. Fail fast so we can retry instead of waiting 180 s.
        fast_fail_markers = (
            b"has disappeared",
            b"Downlink connect needs port number",
            b"Failure with",
            b"No route to",
        )
        while time.monotonic() < deadline:
            self.recv_buf += self.drain(timeout=0.5)
            buf = self.recv_buf
            if b"Please enter your Name" in buf:
                self.send(self.p.nick)
                time.sleep(3)
                self.drain(timeout=2)
                in_chat = True
                break
            if any(m in buf for m in in_chat_markers):
                in_chat = True
                break
            for fm in fast_fail_markers:
                if fm in buf:
                    tail = buf[-200:].decode("utf-8", "replace").strip()
                    raise RuntimeError(f"chat connect rejected: {tail!r}")
        if not in_chat:
            tail = self.recv_buf[-200:].decode("utf-8", "replace")
            raise TimeoutError(f"chat did not respond in 180 s; last bytes: {tail!r}")
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

    # Markers that mean we're not in chat any more — either an explicit
    # disconnect or output that's coming from BPQ's node prompt rather
    # than the chat server.
    _BACK_AT_NODE_MARKERS = (
        b"Invalid command",
        b"Disconnected from Node",
        b"Disconnected from Stream",
        b"Connect refused",
    )

    def looks_dropped(self, buf: bytes) -> bool:
        """True if recent output indicates we're no longer in chat."""
        for m in self._BACK_AT_NODE_MARKERS:
            if m in buf:
                return True
        return False

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

def director(sessions: dict[str, Session], stop: threading.Event) -> None:
    """Play threads at random with brisk cadence and short quiet gaps.

    Returns when `stop` is set. The check happens both between messages
    and during the inter-thread quiet period so a STOP request lands
    within a few seconds at worst.
    """
    rng = random.Random(os.environ.get("CHATBOT_SEED") or None)

    # Pacing — overridable via env so the cadence can be tuned without
    # editing the script. Defaults are deliberately chatty.
    msg_min = float(os.environ.get("CHATBOT_MSG_MIN_S", "8"))
    msg_max = float(os.environ.get("CHATBOT_MSG_MAX_S", "30"))
    gap_min = float(os.environ.get("CHATBOT_GAP_MIN_S", "20"))
    gap_max = float(os.environ.get("CHATBOT_GAP_MAX_S", "90"))

    def reconnect(speaker: str, sess: Session) -> bool:
        """Tear down a session and bring it back up. Returns True on success."""
        try:
            sess.close()
        except Exception:
            pass
        try:
            sess.connect()
            sess.login_and_enter_chat()
            return True
        except Exception as e:
            print(f"[{speaker}] reconnect failed: {e}", flush=True)
            return False

    while not stop.is_set():
        thread = rng.choice(THREADS)
        print(f"\n--- starting thread ({len(thread)} lines) ---", flush=True)
        for speaker, text in thread:
            # Per-message delay before the line lands. interruptible_sleep
            # returns early if stop is set so STOP lands in <1 s.
            if interruptible_sleep(stop, rng.uniform(msg_min, msg_max)):
                return
            sess = sessions.get(speaker)
            if sess is None:
                continue
            print(f"[{speaker}] {text}", flush=True)

            def attempt_say() -> tuple[bool, bytes]:
                """Send text, drain reply briefly, return (ok, raw_reply)."""
                try:
                    sess.send(text)
                except OSError as e:
                    return False, str(e).encode()
                # Give BPQ a moment to surface any "Invalid command" /
                # "Disconnected" line back at us.
                reply = sess.drain(timeout=0.6)
                if sess.looks_dropped(reply):
                    return False, reply
                return True, reply

            ok, reply = attempt_say()
            if not ok:
                snippet = reply[-120:].decode("utf-8", "replace").strip()
                print(f"[{speaker}] dropped from chat ({snippet!r}); reconnecting",
                      flush=True)
                if reconnect(speaker, sess):
                    # Try one more time after rejoining.
                    ok, reply = attempt_say()
                    if not ok:
                        print(f"[{speaker}] still dropped after rejoin; skip line",
                              flush=True)
            # Keep other sessions alive (drain idle inbound). Also
            # check them for drop markers so a quiet-chat persona
            # whose session died gets repaired before the director's
            # next pick.
            for other_name, other in sessions.items():
                if other is sess:
                    continue
                try:
                    leaked = other.drain(timeout=0.1)
                except OSError:
                    leaked = b""
                if leaked and other.looks_dropped(leaked):
                    print(f"[{other_name}] noticed drop; reconnecting", flush=True)
                    reconnect(other_name, other)
        gap = rng.uniform(gap_min, gap_max)
        print(f"--- thread done; quiet for {gap:.0f}s ---", flush=True)
        # Keepalive throughout the quiet period.
        end = time.monotonic() + gap
        while time.monotonic() < end and not stop.is_set():
            for s in sessions.values():
                try:
                    s.keepalive()
                except OSError:
                    pass
            if interruptible_sleep(stop, 5):
                return


def interruptible_sleep(stop: threading.Event, seconds: float) -> bool:
    """Sleep up to `seconds`, returning True if stop was set during it."""
    return stop.wait(timeout=seconds)


# ---------------------------------------------------------------------------
# Controller — owns the start/stop state machine + HTTP control plane
# ---------------------------------------------------------------------------

class Controller:
    """State machine wrapping persona connect + director thread.

    States:
      stopped  — no sessions, director thread not running. Default at boot.
      running  — all personas connected, director thread cycling threads.

    start() and stop() are idempotent and safe to call from any thread.
    The HTTP control plane drives them.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._stop.set()                       # default: stopped
        self._sessions: dict[str, Session] = {}
        self._director_thread: threading.Thread | None = None
        self._state = "stopped"

    def state(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": self._state,
                "personas": [p.nick for p in PERSONAS],
                "connected": list(self._sessions.keys()),
            }

    def start(self) -> dict[str, object]:
        with self._lock:
            if self._state == "running":
                return self._snapshot_unlocked()
            self._state = "starting"
        try:
            # Open all four personas in parallel — sequential start was
            # bottlenecking on the first chat connect's L4 path setup,
            # making the second persona's 180 s budget run out before
            # NETROM was ready for another circuit.
            sessions: dict[str, Session] = {}
            errors: dict[str, Exception] = {}
            sessions_lock = threading.Lock()

            def open_one(p: Persona) -> None:
                last_err: Exception | None = None
                # Up to 3 attempts: NETROM aliases can be transiently
                # missing from a station's table, especially right
                # after a restart cycle. A 45 s backoff lets the next
                # NODES broadcast refresh it.
                for attempt in range(3):
                    s = Session(p)
                    try:
                        s.connect()
                        s.login_and_enter_chat()
                        with sessions_lock:
                            sessions[p.nick] = s
                        return
                    except Exception as e:
                        last_err = e
                        try:
                            s.close()
                        except Exception:
                            pass
                        if attempt < 2:
                            print(f"[{p.nick}] attempt {attempt + 1} failed ({e}); retrying in 45 s",
                                  flush=True)
                            time.sleep(45)
                with sessions_lock:
                    errors[p.nick] = last_err

            threads = [
                threading.Thread(target=open_one, args=(p,), name=f"open-{p.nick}", daemon=True)
                for p in PERSONAS
            ]
            for t in threads:
                t.start()
                time.sleep(0.5)  # tiny stagger so the BPQ telnets don't all arrive on the same ms
            for t in threads:
                t.join()
            if errors:
                # Even one persona failing is OK — the others can chat —
                # but log every failure so it's diagnosable.
                for nick, err in errors.items():
                    print(f"[{nick}] join failed: {err}", flush=True)
            if not sessions:
                raise RuntimeError(
                    "no personas could join chat: " +
                    ", ".join(f"{k}={v}" for k, v in errors.items())
                )
            print(f"{len(sessions)}/{len(PERSONAS)} personas joined chat", flush=True)
            with self._lock:
                self._sessions = sessions
                self._stop = threading.Event()
                t = threading.Thread(
                    target=director,
                    args=(self._sessions, self._stop),
                    name="director",
                    daemon=True,
                )
                self._director_thread = t
                self._state = "running"
            t.start()
        except Exception as e:
            print(f"start failed: {e}", flush=True)
            with self._lock:
                for s in sessions.values() if 'sessions' in locals() else []:
                    try:
                        s.close()
                    except Exception:
                        pass
                self._sessions = {}
                self._state = "stopped"
            raise
        return self.state()

    def stop(self) -> dict[str, object]:
        with self._lock:
            if self._state == "stopped":
                return self._snapshot_unlocked()
            self._state = "stopping"
            self._stop.set()
            sessions = list(self._sessions.values())
            self._sessions = {}
            t = self._director_thread
            self._director_thread = None
        # Outside lock — director may need to acquire something while
        # exiting its loop. Wait briefly for clean exit.
        if t is not None:
            t.join(timeout=10)
        for s in sessions:
            try:
                s.close()
            except Exception:
                pass
        with self._lock:
            self._state = "stopped"
        return self.state()

    def _snapshot_unlocked(self) -> dict[str, object]:
        return {
            "state": self._state,
            "personas": [p.nick for p in PERSONAS],
            "connected": list(self._sessions.keys()),
        }


# ---------------------------------------------------------------------------
# Tiny HTTP control plane
# ---------------------------------------------------------------------------

import http.server
import json
import urllib.parse


def make_http_handler(ctrl: Controller):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Quieter logs — we don't need the access log noise.
            print("ctrl http: " + (fmt % args), flush=True)

        def _send_json(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.end_headers()

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path == "/state":
                self._send_json(200, ctrl.state())
            else:
                self._send_json(404, {"error": "not found"})

        def do_POST(self):
            path = urllib.parse.urlparse(self.path).path
            try:
                if path == "/start":
                    self._send_json(200, ctrl.start())
                elif path == "/stop":
                    self._send_json(200, ctrl.stop())
                else:
                    self._send_json(404, {"error": "not found"})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
    return Handler


def main() -> int:
    # Boot-stagger so the BPQ nodes have a chance to come up if we were
    # started in the same compose `up`. Affects only the first /start.
    time.sleep(int(os.environ.get("CHATBOT_BOOT_DELAY", "20")))

    ctrl = Controller()
    addr = ("0.0.0.0", int(os.environ.get("CHATBOT_HTTP_PORT", "8090")))
    server = http.server.ThreadingHTTPServer(addr, make_http_handler(ctrl))
    print(f"chatbot HTTP control on {addr[0]}:{addr[1]}", flush=True)

    auto = os.environ.get("CHATBOT_AUTOSTART", "0") == "1"
    if auto:
        try:
            ctrl.start()
        except Exception as e:
            print(f"autostart failed: {e}", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            ctrl.stop()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
