# Synthetic packet-radio test network

A docker-compose stack that builds a small but varied "RF" network you can
attach your real packet node to. Inside the stack there are 14 BPQ
stations across 5 simulated towns, connected by 5 inter-town backbone
links. Some of those stations also host applications — BBS Mail in
Aberdeen, Bristol and Exeter; a chat server in Durham — addressed at
additional SSIDs on the host station's callsign, the way real packet
sites do it.

All callsigns/aliases start with `Q` so they cannot collide with real
licensed amateur callsigns.

## Nodes vs applications

A BPQ **station** is one machine with one or more radios. It has a
**node callsign** for the routing layer (e.g. `QA0HUB-7`), and may
host one or more **applications** — BBS, chat, RMS gateway etc. —
addressed at *additional SSIDs on the same base callsign*: the
Aberdeen BBS is `QA0HUB-1`, the Durham chat is `QD0HUB-2`. These
share the station's one radio and appear in the NETROM nodes table
as additional aliases pointing to the same L2 destination.

So there are 14 *stations* in this test net, of which 4 also host an
application (3 BBSes + 1 chat). The Cambridge town has no application
host. To connect to the Aberdeen BBS, you `C BBS` (the alias) or
`C QA0HUB-1` (the SSID directly) — both reach the BBS process living
on the same machine as the Aberdeen hub.

```
                                 [ il2p 9k6 ]
                  ┌──────────────────────────────────────┐
                  │                                      │
  ABERDEEN ─9k6─ DURHAM ─9k6─ CAMBRIDGE ─9k6─ BRISTOL ─9k6─ EXETER
   (4 nodes)    (4 nodes)    (3 nodes)       (3 nodes)     (4 nodes)
      ▲
      │
   YOUR REAL NODE attaches here  (host TCP/8100, KISS over TCP)
```

## What's in it

* **1 net-sim container** running the entire RF simulation. Inside it every
  `Q*` node has one or more "radios" (samoyed modem processes), each exposed
  as a KISS-over-TCP port. The container's `network.yaml` describes channel
  membership and per-pair path loss (so hidden-node and FM-capture effects
  are modelled).
* **14 linbpq containers** — one per `Q*` station. Each runs `m0lte/linbpq`
  and attaches its `bpq32.cfg` PORT(s) to the appropriate netsim KISS
  port(s). Four of them also host BPQ Mail or BPQ Chat (started with
  the corresponding extra `command:` in compose).

### Stations

| Station     | Alias  | Town       | Role                      | Radios | Hosted apps               |
|-------------|--------|------------|---------------------------|--------|---------------------------|
| QA0ABN-7    | ABENOR | Aberdeen   | User                      | 1      | —                         |
| QA0ABS-7    | ABESTH | Aberdeen   | User                      | 1      | —                         |
| QA0HUB-7    | ABEHUB | Aberdeen   | Hub (town + 9k6 backbone) | 2      | BBS at `QA0HUB-1` (`BBS`) |
| QB0BRI-7    | BRIMAI | Bristol    | User                      | 1      | —                         |
| QB0HUB-7    | BRIHUB | Bristol    | Hub                       | 4      | BBS at `QB0HUB-1` (`BBS`) |
| QC0CAM-7    | CAMNOR | Cambridge  | User                      | 1      | —                         |
| QC0CAS-7    | CAMSTH | Cambridge  | User                      | 1      | —                         |
| QC0HUB-7    | CAMHUB | Cambridge  | Hub                       | 3      | —                         |
| QD0DUR-7    | DURNOR | Durham     | User                      | 1      | —                         |
| QD0DUS-7    | DURSTH | Durham     | User                      | 1      | —                         |
| QD0HUB-7    | DURHUB | Durham     | Hub                       | 4      | Chat at `QD0HUB-2` (`CHT`)|
| QE0EXE-7    | EXENOR | Exeter     | User                      | 1      | —                         |
| QE0EXS-7    | EXESTH | Exeter     | User                      | 1      | —                         |
| QE0HUB-7    | EXEHUB | Exeter     | Hub                       | 2      | BBS at `QE0HUB-1` (`BBS`) |

### Channels / RF topology

* 5 **town channels** (afsk1200, simplex). Nodes in a town all share their
  town channel — so they collide if they transmit simultaneously, hear each
  other subject to FM capture, etc.
* 5 **backbone links** (gfsk9600, point-to-point). Each is its own
  channel with only the two HUB ports linked, so no contention.
  * ABE ↔ DUR
  * DUR ↔ CAM
  * CAM ↔ BRI
  * BRI ↔ EXE
  * DUR ↔ BRI (this one is **il2p** with strong FEC, slightly higher loss —
    so NETROM prefers it for the Durham/Bristol diagonal).

### Hidden-node pairs

To exercise the contention behaviour you said you wanted:

* **Aberdeen**: QA0ABN ↔ QA0ABS (35 dB between them, but both heard cleanly
  by QA0HUB).
* **Durham**: QD0DUR ↔ QD0DUS (42 dB), both fully heard by QD0HUB.
* **Cambridge & Exeter** have one moderate-loss pair each (25 / 20 dB) — they
  can still hear each other but not as cleanly as everything else.

## Bringing it up

Prerequisites: a working Docker installation that includes Docker
Compose v2 (`docker compose ...`). Tested on Docker Desktop / WSL2,
should work on any Linux host with Docker ≥ 24.

```
git clone https://github.com/M0LTE/test-net.git
cd test-net
docker compose up -d
```

First pull of `ghcr.io/packethacking/net-sim:main` and
`m0lte/linbpq:latest` will take a minute. The 14 linbpq containers
wait for net-sim's healthcheck to pass before starting. NETROM
neighbours appear within ~30 s; the full mesh takes roughly 5 minutes
to converge from cold.

To tear the network down again:

```
docker compose down
```

`docker compose down` removes the containers and the Docker network
but leaves your `nodes/<call>/` directories on disk, including each
node's `BPQNODES.dat` and chat/BBS state. The next `up` resumes from
that state so reconvergence is fast. To start completely fresh, also
delete `nodes/*/BPQNODES.dat` `nodes/*/HTML` `nodes/*/logs` (or just
let `.gitignore` show you what's runtime state).

### Optional: docker socket for sim-only CPU%

The live map (`/map`, see below) shows aggregate CPU% across this
sim's containers when net-sim can talk to the Docker daemon. The
compose mounts `/var/run/docker.sock` read-only and adds the netsim
container to the host's `docker` group. On most distros that group
is GID 999 or 1001; the compose defaults to 1001. If your host
uses a different GID, run with an override:

```
DOCKER_SOCK_GID=$(stat -c %g /var/run/docker.sock) docker compose up -d
```

If the socket isn't readable for any reason, `/api/stats` falls
back to host-wide CPU and the HUD label changes to `HOST CPU`.

## Attaching your real packet node

net-sim publishes one extra KISS port for you to attach to. From your real
packet node, add a KISS-over-TCP port pointing at:

```
host:   <docker-host-ip>   (e.g. 127.0.0.1 if running locally)
port:   8100
mode:   AFSK 1200 (you'll appear on the Aberdeen town channel)
```

In linbpq, that looks like:

```
PORT
 ID=Synthetic test net
 TYPE=ASYNC
 PROTOCOL=KISS
 IPADDR=127.0.0.1
 TCPPORT=8100
 SPEED=1200
 CHANNEL=A
 QUALITY=192
 MAXFRAME=4
 PACLEN=120
ENDPORT
```

Once linked, all 14 station node calls plus their hosted-application
aliases (`BBS:QA0HUB-1`, `BBS:QB0HUB-1`, `BBS:QE0HUB-1`, `CHT:QD0HUB-2`)
should appear in your `N` (nodes) table. From any station you can
`C QA0HUB-7` to drop into the Aberdeen hub's node prompt, `C BBS`
(via NETROM) or `C QA0HUB-1` to land in the Aberdeen BBS, `C CHT`
or `C QD0HUB-2` to land in the Durham chat — each cross-town hop
travels the synthetic backbone.

## Reaching the synthetic nodes

Every linbpq container publishes three TCP ports on the host:
**HTTP** (BPQ web UI), **Telnet** (BPQ node console), and **FBB**
(QtTermTCP's "BPQ via FBB" connection mode). Credentials and the
top-level sysop password are identical on every node — see below
the table.

| Station  | Alias  | Call       | HTTP                   | Telnet  | FBB     |
|----------|--------|------------|------------------------|---------|---------|
| QA0ABN   | ABENOR | QA0ABN-7   | http://localhost:18001 | 18101   | 18201   |
| QA0ABS   | ABESTH | QA0ABS-7   | http://localhost:18002 | 18102   | 18202   |
| QA0HUB   | ABEHUB | QA0HUB-7   | http://localhost:18004 | 18104   | 18204   |
| QB0BRI   | BRIMAI | QB0BRI-7   | http://localhost:18005 | 18105   | 18205   |
| QB0HUB   | BRIHUB | QB0HUB-7   | http://localhost:18007 | 18107   | 18207   |
| QC0CAM   | CAMNOR | QC0CAM-7   | http://localhost:18008 | 18108   | 18208   |
| QC0CAS   | CAMSTH | QC0CAS-7   | http://localhost:18009 | 18109   | 18209   |
| QC0HUB   | CAMHUB | QC0HUB-7   | http://localhost:18010 | 18110   | 18210   |
| QD0DUR   | DURNOR | QD0DUR-7   | http://localhost:18011 | 18111   | 18211   |
| QD0DUS   | DURSTH | QD0DUS-7   | http://localhost:18012 | 18112   | 18212   |
| QD0HUB   | DURHUB | QD0HUB-7   | http://localhost:18014 | 18114   | 18214   |
| QE0EXE   | EXENOR | QE0EXE-7   | http://localhost:18015 | 18115   | 18215   |
| QE0EXS   | EXESTH | QE0EXS-7   | http://localhost:18016 | 18116   | 18216   |
| QE0HUB   | EXEHUB | QE0HUB-7   | http://localhost:18018 | 18118   | 18218   |

**Credentials (same on every node):**

| Where                 | Username | Password   |
|-----------------------|----------|------------|
| HTTP web UI / sysop   | `admin`  | `admin`    |
| Telnet console        | `user`   | `pass`     |
| FBB (QtTermTCP)       | `user`   | `pass`     |
| Sysop `?PASS` reply   | —        | `letmein`  |

Both `admin` and `user` are flagged `SYSOP` so sysop commands work
either way; the split exists so the docs can call them "HTTP" vs
"console" credentials without further nuance.

To change them, edit each `nodes/<call>/bpq32.cfg`'s Telnet `PORT`
block. Don't expose these ports to anything but localhost — these
defaults are deliberately weak.

### Live map and topology dashboard

net-sim's own dashboards are served by the netsim container:

* <http://localhost:8080> — topology editor / Start/Stop/Restart
* <http://localhost:8080/map> — live DEFCON-flavour situation display.
  Topology clustered by detected town, links light up as they carry
  traffic, per-frame missile-arc pulses along each edge, HUD with
  events-per-second, TX-active count, collision/capture counters, and
  a sim-CPU sparkline. The external attach point (USEREXT) is rendered
  as a distinct amber diamond rather than a regular station so it
  reads as "outside world."

## Useful sanity checks

From any node's Telnet console:

* `PORTS`  — list this node's RF ports (you should see VHF + any backbones).
* `N`      — NETROM nodes table. After a couple of minutes you should see
             all 17 other `Q*` nodes.
* `R`      — routes (adjacent neighbours).
* `MH 1`   — heard list on port 1 (RF).
* `C QE0HUB-7` from QA0ABN — connect across the whole network.
* `BYE`    — disconnect.

## Layout

```
test-net/
├── docker-compose.yml
├── netsim/
│   └── network.yaml           # the entire RF topology
└── nodes/
    ├── QA0ABN/bpq32.cfg       # one dir per node, mounted as /data
    ├── QA0ABS/bpq32.cfg
    ├── ... (16 more)
    └── QE0HUB/bpq32.cfg
```

Each `nodes/<call>/` directory will also fill up with runtime state
(`BPQNODES.dat`, `*.mes`, `logs/`, `HTML/`) once the stack runs — those are
created by linbpq itself inside the bind-mount.

## Tweaking

* **More/fewer nodes**: add or remove a service block in
  `docker-compose.yml`, add a matching `nodes/<call>/bpq32.cfg`, and add the
  corresponding port + links to `netsim/network.yaml`.
* **Different channel topology**: edit the `links:` section of
  `netsim/network.yaml`. Each link is one-way, so you need a pair of entries
  for any bidirectional path. Bump `loss_db` to hide nodes from each other.
* **Routing preferences**: change `QUALITY=` on the backbone PORT blocks
  inside each HUB's `bpq32.cfg`. Higher quality means NETROM prefers that
  hop. 1200 town channels are 192; 9k6 backbones are 230; il2p is 240.

## Notes / caveats

* This stack is for testing only — sysop password is `changeme` and ports
  are bound on `0.0.0.0` (host-wide). Don't expose to the public internet.
* The chat node uses linbpq's built-in chat (BPQChat). Connect `C CHT` from
  anywhere in the network and you'll be dropped into the chat prompt.
* `bpq32.cfg`'s exact KISS-over-TCP syntax (`TYPE=ASYNC` + `PROTOCOL=KISS` +
  `IPADDR=...` + `TCPPORT=...`) is the same form used to attach BPQ to a
  Direwolf running on another host — net-sim's KISS ports are protocol-
  identical to Direwolf's.
* **linbpq does not resolve hostnames in `IPADDR=`** — every cfg uses the
  static IP `172.28.0.10`, and `docker-compose.yml` pins that to the
  `netsim` container via an explicit `ipv4_address` on the `rfnet` bridge.
  If you change the subnet, update both.
* **`IDINTERVAL=0` is mandatory here (workaround).** net-sim's modem
  backend (samoyed) panics on AX.25 UI frames with an empty info field
  (samoyed [#504](https://github.com/doismellburning/samoyed/issues/504)),
  which is exactly what BPQ's port-ID broadcast looks like. One crash
  kills every samoyed on the channel and the simulator stops carrying
  packets. With `IDINTERVAL=0` the ID beacon is suppressed and the
  simulator stays up. (NETROM `NODES` broadcasts have a non-empty
  info field and don't trip the bug.) Upstream fix is
  [samoyed#506](https://github.com/doismellburning/samoyed/pull/506),
  merged 2026-05-06, but the published `ghcr.io/packethacking/net-sim:main`
  image hasn't picked it up yet because the Dockerfile's
  `git clone --branch main` step is cached at the GHA layer cache.
  Once a fresh net-sim image ships with samoyed `main` past
  c2301517, you can remove this workaround.
