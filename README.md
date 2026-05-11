# Synthetic packet-radio test network

A docker-compose stack that builds a small but varied "RF" network you can
attach your real packet node to. Inside the stack there are 18 BPQ nodes
across 5 simulated towns, connected by 5 inter-town backbone links.

All callsigns/aliases start with `Q` so they cannot collide with real
licensed amateur callsigns.

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
* **18 linbpq containers** — one per `Q*` node. Each runs `m0lte/linbpq` and
  attaches its `bpq32.cfg` PORT(s) to the appropriate netsim KISS port(s).

### Nodes (callsign-7, alias, role, town)

| Call       | Alias  | Town       | Role              | Ports |
|------------|--------|------------|-------------------|-------|
| QA0ABN-7   | ABENOR | Aberdeen   | User node         | 1     |
| QA0ABS-7   | ABESTH | Aberdeen   | User node         | 1     |
| QA0BBS-7   | ABEBBS | Aberdeen   | **BBS**           | 1     |
| QA0HUB-7   | ABEHUB | Aberdeen   | Hub (town + 9k6)  | 2     |
| QB0BRI-7   | BRIMAI | Bristol    | User node         | 1     |
| QB0BBS-7   | BRIBBS | Bristol    | **BBS**           | 1     |
| QB0HUB-7   | BRIHUB | Bristol    | Hub               | 4     |
| QC0CAM-7   | CAMNOR | Cambridge  | User node         | 1     |
| QC0CAS-7   | CAMSTH | Cambridge  | User node         | 1     |
| QC0HUB-7   | CAMHUB | Cambridge  | Hub               | 3     |
| QD0DUR-7   | DURNOR | Durham     | User node         | 1     |
| QD0DUS-7   | DURSTH | Durham     | User node         | 1     |
| QD0CHT-7   | DURCHT | Durham     | **Chat server**   | 1     |
| QD0HUB-7   | DURHUB | Durham     | Hub               | 4     |
| QE0EXE-7   | EXENOR | Exeter     | User node         | 1     |
| QE0EXS-7   | EXESTH | Exeter     | User node         | 1     |
| QE0BBS-7   | EXEBBS | Exeter     | **BBS**           | 1     |
| QE0HUB-7   | EXEHUB | Exeter     | Hub               | 2     |

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
  by QA0HUB and QA0BBS).
* **Durham**: QD0DUR ↔ QD0DUS (30 dB), both fully heard by QD0HUB and QD0CHT.
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
`m0lte/linbpq:latest` will take a minute. The 18 linbpq containers
wait for net-sim's healthcheck to pass before starting. NETROM
neighbours appear within ~30 s; the full 18-node mesh takes roughly
7 minutes to converge from cold.

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

Once linked, you should see all 18 `Q*` nodes appear in your `N` (nodes)
table and be able to `C QA0HUB-7`, `C QD0CHT-7`, `C QE0BBS-7` etc. — and
each step beyond Aberdeen should route across the synthetic RF backbone.

## Reaching the synthetic nodes from a browser

Every linbpq container exposes its HTTP and Telnet ports on the host:

| Node     | HTTP                  | Telnet              |
|----------|------------------------|---------------------|
| QA0ABN   | http://localhost:18001 | telnet localhost 18101 |
| QA0ABS   | http://localhost:18002 | telnet localhost 18102 |
| QA0BBS   | http://localhost:18003 | telnet localhost 18103 |
| QA0HUB   | http://localhost:18004 | telnet localhost 18104 |
| QB0BRI   | http://localhost:18005 | telnet localhost 18105 |
| QB0BBS   | http://localhost:18006 | telnet localhost 18106 |
| QB0HUB   | http://localhost:18007 | telnet localhost 18107 |
| QC0CAM   | http://localhost:18008 | telnet localhost 18108 |
| QC0CAS   | http://localhost:18009 | telnet localhost 18109 |
| QC0HUB   | http://localhost:18010 | telnet localhost 18110 |
| QD0DUR   | http://localhost:18011 | telnet localhost 18111 |
| QD0DUS   | http://localhost:18012 | telnet localhost 18112 |
| QD0CHT   | http://localhost:18013 | telnet localhost 18113 |
| QD0HUB   | http://localhost:18014 | telnet localhost 18114 |
| QE0EXE   | http://localhost:18015 | telnet localhost 18115 |
| QE0EXS   | http://localhost:18016 | telnet localhost 18116 |
| QE0BBS   | http://localhost:18017 | telnet localhost 18117 |
| QE0HUB   | http://localhost:18018 | telnet localhost 18118 |

Default login on every node: `admin` / `changeme` (sysop). Edit each
`nodes/<call>/bpq32.cfg` to change.

net-sim's own topology dashboard is at <http://localhost:8080>.

Live map (DEFCON-flavour situation display) at
<http://localhost:8080/map> — shows the topology clustered by detected
town, lights links up as they carry traffic, animates per-frame pulses
along each link, and displays a HUD with events-per-second, TX-active
count, collision/capture counters, and a sim-CPU sparkline. The
external attach point (USEREXT) is rendered as a distinct amber
diamond rather than a regular station so it reads as "outside world."

## QtTermTCP / BPQ FBB login

Two nodes expose BPQ's FBB-style TCP port (`FBBPORT`) for QtTermTCP's
"BPQ via FBB" connection mode — `QD0HUB` and `QA0ABS`. All others have
only Telnet + HTTP. Credentials are identical:

| Node | FBB port (host) | Telnet port (host) | Username | Password |
|---|---|---|---|---|
| QD0HUB-7 | 18214 | 18114 | `tom` | `packet` |
| QA0ABS-7 | 18202 | 18102 | `tom` | `packet` |

For other nodes, use QtTermTCP's plain "Telnet" mode against the host
port listed in the table above (host port `18101` for QA0ABN, `18102`
for QA0ABS, etc.) with the same credentials.

Sysop `?PASS` challenge is `letmein` on the FBB-enabled nodes.

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
