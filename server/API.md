# PNPP Server API

`server.py` serves two things on one port: the browser control page (`/`, `/status`,
`/control`) and the JSON API the Unity client joins (`/api/...`).

```bash
cd server-python
python server.py --host 127.0.0.1 --port 8000
```

Routing lives in `api.py`. There are two data files, with different jobs:

| File | What it is | Read by |
| --- | --- | --- |
| `data/control_room_template.json` | the blueprint - panels, names, annunciator layout. Re-read per request. | `GET /api/template` |
| `data/io_definitions.json` | live I/O - switch positions, indicator lamps, gauge values, keyed by definition UID. Held in memory by `io_state.py`. | `GET /api/io`, `POST /api/io/*` |

Both use the same UID space: a template entry's `definitionId` and an I/O entry's
`uid` are the same Unity definition UID.

All API responses are JSON with `Access-Control-Allow-Origin: *` (needed by WebGL
builds and the control page; the Unity editor ignores CORS).

## Endpoints

### `GET /api`

Version + endpoint list. Cheap liveness check.

```json
{ "apiVersion": 1, "endpoints": ["/api", "/api/info", "/api/template", "..."] }
```

### `GET /api/info`

Handshake. The client's join screen calls this first: a response without
`apiVersion` means "not a PNPP server", and `scene` tells the client which Unity
scene this session belongs in.

```json
{
  "server": "PNPP Python Server",
  "apiVersion": 1,
  "templateVersion": 1,
  "plantName": "Phoenix Nuclear Power Plant",
  "unit": 1,
  "reactorType": "PWR",
  "scene": "MainScene",
  "players": 0,
  "maxPlayers": 8,
  "host": "127.0.0.1",
  "port": 8000,
  "endpoints": ["/api", "/api/info", "/api/template"]
}
```

`players` is a placeholder — there is no session tracking yet.

### `GET /api/template`

The control-room template: everything the client needs to know which controls
exist and what state the server holds for them. Sections:

| Section | What's in it |
| --- | --- |
| `plant` | id, name, unit, reactor type, scene |
| `panels` | panel ids the controls group under (`MCR`, `SICS`, `RCP`, ...) |
| `switches` | id, definitionId, panel, controller, positions, current position, powered, available, indicator |
| `annunciators` | id, legend text, tile row/column, priority, state, flashing, acknowledged, colour |
| `gauges` | id, definitionId, panel, units, min/max, current value, valid |
| `breakers` | id, panel, switch state, indicator state, powered, available |

Unknown endpoints answer `404` with a JSON body listing the valid ones.

### `GET /api/io`

Live I/O state. `?since=<revision>` returns only entries that changed after that
revision; without it you get the whole map. `?clientId=<id>` leaves out entries
that client itself last wrote.

```json
{
  "sessionId": "c01b79468d9a4ba0ae86a300a42ae50f",
  "revision": 14,
  "reportIntervalSeconds": 0.2,
  "switches":   [{"uid": "...", "id": "RCP_1_Power", "name": "RCP 1 Power",
                  "positions": ["off", "on"], "position": "on",
                  "powered": true, "available": true, "revision": 12}],
  "indicators": [{"uid": "...", "id": "RCP_1_LAMP", "name": "RCP 1 Lamp",
                  "state": "red", "flashing": false, "revision": 13}],
  "gauges":     [{"uid": "...", "id": "RCP_1_HZ", "name": "RCP 1 Speed", "units": "Hz",
                  "minValue": 0.0, "maxValue": 80.0, "value": 50.0,
                  "valid": true, "revision": 14}]
}
```

Entries are always whole, never partial, and sorted by `revision`.

`revision` is a single counter over all three collections: every change takes the
next number. That's what makes `?since=` cheap and exact.

`sessionId` changes when the server restarts or reloads its definitions —
revisions start over then, so a client that sees a new session id must resync
from scratch (the Unity client does this automatically).

### `POST /api/io/report`

What the Unity client calls on a timer. It sends the position of every switch
definition it holds; the response is everything that client hasn't seen yet — the
same shape as `GET /api/io`, plus the outcome of the report.

```json
{ "clientId": "3f2b8c1d...", "since": 12,
  "switches": [{"uid": "...", "id": "RCP_1_Power", "name": "RCP 1 Power",
                "positions": ["off", "on"], "position": "on"}] }
```

`id`, `name` and `positions` only matter the first time the server sees a uid
(auto-registration). The client doesn't send `powered`/`available` — it has no
opinion on those, and reporting them would clobber the server's.

Response adds:

| Field | Meaning |
| --- | --- |
| `accepted` | uids whose reported position was taken |
| `rejected` | uids where the server had a newer value; the current one is in `switches` |
| `unknown` | uids with no definition (and auto-registration off) |
| `registered` | uids the server just auto-registered |

**Why reports can be rejected:** clients report every switch every tick, so two
clients with different stale views would otherwise flip a switch back and forth.
A reported change is only taken if the client had already seen that switch's
current value (its `revision` is `<= since`). Otherwise it's rejected and the
correct value comes back in the same response, so the client self-corrects on the
next frame.

### `POST /api/io/set`

Server-authoritative write. Any mix of the three collections; unknown uids come
back in `unknown` (this writes to definitions, it doesn't create them).

```json
{ "gauges":     [{"uid": "...", "value": 47.5, "valid": true}],
  "indicators": [{"uid": "...", "state": "red", "flashing": true}],
  "switches":   [{"uid": "...", "position": "on", "powered": true}] }
```

→ `{"revision": 15, "changed": ["..."], "unknown": []}`

### `POST /api/io/save`

Writes current I/O values back to `data/io_definitions.json`.
→ `{"saved": "<path>", "revision": 15}`

## The I/O map (`data/io_definitions.json`)

Ships empty. Three collections plus config:

```json
{ "ioVersion": 1, "reportIntervalSeconds": 0.2, "autoRegisterFromClients": true,
  "switches": [], "indicators": [], "gauges": [] }
```

| Key | Effect |
| --- | --- |
| `reportIntervalSeconds` | how often the client exchanges data; sent to the client, which adopts it |
| `autoRegisterFromClients` | add switches the client reports but this file doesn't have. On by default, so the file fills itself from the scene; turn it off once the map is settled and unknown uids will be reported instead |

**Indicators are keyed by the switch's uid** — a lamp pair belongs to a switch, so
`SwitchLampIndicator` and its `Rot2p` share a UID, in different collections.

Editing while the server runs: it owns the file at runtime and rewrites it when a
definition appears or you call `save()`. Edit it stopped, or call
`state.reload()` after editing (that resets values and forces clients to resync).

`revision` and `updatedBy` are runtime bookkeeping and stay out of the file.

## Reading and writing state from Python

`io_state.py` holds one shared `IoState`. Import it wherever the simulation
lives — the HTTP handlers and your own code use the same object, and every method
takes a lock, so a background sim thread is fine.

```python
from io_state import state

# define (persists to the JSON immediately)
state.define_gauge("33bee2dd-...", id="RCP_1_HZ", name="RCP 1 Speed",
                   units="Hz", min_value=0.0, max_value=80.0)
state.define_indicator("a250f6ec-...", id="RCP_1_LAMP", state="green")
state.define_switch("a250f6ec-...", id="RCP_1_POWER", positions=["off", "on"])

# read
pump = state.get_switch("a250f6ec-...")     # dict, or None
if pump["position"] == "on" and pump["powered"]:
    ...
state.switches(); state.indicators(); state.gauges()   # whole collections

# write - each returns True if something actually changed
state.set_gauge("33bee2dd-...", 50.0)                  # the client's needle follows
state.set_indicator("a250f6ec-...", "red", flashing=True)
state.set_switch("a250f6ec-...", position="on")        # moves it for every player
state.set_switch("a250f6ec-...", powered=False)

state.save()        # values -> JSON
state.reload()      # JSON -> values (clients resync)
```

Notes:

- Values are clamped to the gauge's `minValue`/`maxValue`, and a write that
  doesn't change anything (same value, within 1e-6) returns `False` without
  burning a revision — so calling `set_gauge` every tick is fine.
- `set_switch` raises `ValueError` on a position the switch doesn't have;
  `set_*` on an unknown uid returns `False` rather than raising.
- Value changes are **not** auto-saved (they'd rewrite the file constantly).
  Definition changes are.

### The test simulations

Three working examples of the above. `server.py` starts them all automatically;
`--no-sim` runs the server bare. Each defines any of its entries that are
missing on startup (uids are in a table at the top of the file), so they work
before a client ever connects. Use them as the template for future systems: put
your uids in a table, read inputs with `get_switch`, write outputs with
`set_gauge` on a tick.

They also show how systems chain: a gauge one sim writes is the input another
reads (switches → valve position → turbine speed). No wiring needed for that —
they share the one `IoState`, so a sim just reads the uid it cares about.

**`rcp_sim.py`** — four reactor coolant pumps whose frequency gauge follows
their power switch. Switch on runs the pump up toward 60 Hz (τ = 6 s), switch
off coasts it down (τ = 20 s, the flywheel).

**`valve_sim.py`** — the turbine and bypass valves, on three-position (`Rot3p`)
switches: **left strokes the valve closed, right strokes it open, centre holds
it.** Travel is linear at a fixed rate and the position gauge clamps at 0/100 %.

| Switch | Gauge | Rate | Full stroke |
| --- | --- | --- | --- |
| Turbine Valve | Turbine Valve Pos | 4.0 %/s | 25 s |
| Turbine Valve Close | Turbine Valve Pos | 0.1 %/s | 1000 s |
| Bypass Valve | Bypass Valve Pos | 5.0 %/s | 20 s |

Two switches share the turbine valve gauge: the main one, and the "Close" fine
control. That one is a vernier rather than a way to stroke the valve — at
0.1 %/s a second of it is 8 RPM of speed demand or 2.3 MW of load, which is the
resolution you need to land inside the sync band and to trim load. Their rates
sum, so holding both the same way drives the valve at 4.1 %/s. An unpowered
switch contributes nothing.

**`turbine_sim.py`** — the turbine-generator set, from run-up through
synchronising to load. One module rather than three because each stage locks the
next: the breaker fixes the speed, and the speed being fixed is what turns valve
position into megawatts.

*Run-up.* Valve position is the speed demand, straight through and proportional,
pinned to the design point **22.8 % → 1800 RPM** (half speed). That's 78.95 RPM
per % of valve. Speed glides to it as a first-order lag (τ = 30 s), so the
turbine pulls hard while it's a long way out and creeps in over the last few
RPM — 1138 RPM at 30 s, 1710 at 90 s, settling around four minutes. The demand
clamps to the dial for the needle's sake, but **not** for load: past synchronous
speed the surplus is what makes megawatts, so clamping there would cap the
machine at a few MW.

*Synchronising.* The **phase offset** between machine and grid is carried
forward every tick no matter what is displaying it — it's a fact about the two
waveforms, and it goes on drifting while nobody is watching. Slip is the rate:
one full turn per slip cycle, winding forward (clockwise) when the turbine is
the faster, so 5 RPM out is 0.167 Hz of slip and 60 °/s.

The synchroscope only reads that offset out. Switching the **Synchroscope
Toggle** in lands the pointer on the phase as it already stands, rather than
picking up from wherever it was parked. It reads within **±10 RPM** of grid
speed, where the drift is slow enough to follow — further out the pointer is an
unreadable blur, and past ~75 RPM it turns more than half a dial between syncs
and would alias into reading backwards. The offset keeps being tracked either
way, so the dial agrees with it the moment it comes back in band.

*On the grid.* Shutting the **Gen Breaker** inside that band puts the machine on
the grid, and the grid holds it at exactly synchronous speed. Shutting it
outside the band does nothing — that's what makes you sync rather than just
close it. The lock keeps itself true (pinned to grid speed, the band test stays
satisfied), and opening the breaker releases the turbine back to its demand.

*Load.* On the grid the turbine can't accelerate, so demand above synchronous
speed becomes torque: 22.8 % of valve is exactly **0 MW**, wide open is the
Arabelle's rated **1800 MW**, and everything between is proportional at
0.295 MW per RPM of surplus demand. Below 22.8 % the load goes negative — the
machine motoring — and for now the gauge just stops at zero; the reverse-current
annunciator is what will show it. Off the grid, load is 0.

| Signal | Uid | Range | Direction |
| --- | --- | --- | --- |
| Turbine RPM | `3eec464f` | 0–2000 RPM | out |
| Gen Load | `5bda98ec` | 0–2000 MW | out |
| Gen Synchroscope | `5bbbde79` | 0–360° | out |
| Grid Freq. | `d4b07123` | 57–63 Hz | in (sits at 60) |
| Gen Breaker | `24652917` | off/on | in |
| Synchroscope Toggle | `489d8134` | off/on | in |

Grid frequency is an input this never writes, so `POST /api/io/set` can move it
and everything follows: synchronous speed is `gridHz × 30` (4-pole machine), and
the load zero point moves with it. A gradual change keeps the machine locked and
dragged along; only an instantaneous jump of more than 10 RPM (0.33 Hz) breaks
the lock.

> The Unity faces **Turbine RPM** (0–2000) and **Turbine RPM Close** (1795–1805,
> the expanded scale for synchronising) share one uid. The server holds a single
> value over the full range and each needle clips it to its own face, so the
> I/O entry uses the coarse 0–2000 range.

## Editing the template

Add controls by editing `data/control_room_template.json` — no Python changes
needed. Two rules:

1. **camelCase keys, no hyphens.** The Unity client parses with `JsonUtility`,
   which maps JSON keys onto C# field names, and `switch-state` can't be a field
   name. Use `switchState`.
2. **`definitionId` is the Unity UID**, copied from the `SwitchDefinition` /
   `GaugeDefinition` asset (Inspector → three dots → Generate New ID). That's how
   a control in the scene finds its own entry. Leave it `""` for controls the
   server tracks but the scene doesn't model yet.

Adding a field is safe in both directions: `JsonUtility` ignores keys it has no
field for and leaves absent keys at their default. Removing or renaming one is
not — bump `API_VERSION` in `api.py` and `ServerConnection.SupportedApiVersion`
in the client together when the shape changes incompatibly.

## Client side

| Server side | Unity mirror |
| --- | --- |
| `/api/info` | `ServerConnection.ServerInfo` |
| `/api/template` | `ControlRoomTemplate.cs` |
| `/api/io`, `/api/io/report` | `IoPayloads.cs`, driven by `IoSync.cs` |

See `client/unbuilt/docs/joining-a-server.md` and
`client/unbuilt/docs/server-io-sync.md`.
