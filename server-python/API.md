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

### The RCP test simulation (`rcp_sim.py`)

The working example of the above: four reactor coolant pumps whose frequency
gauge follows their power switch — switch on runs the pump up toward 60 Hz
(τ = 6 s), switch off coasts it down (τ = 20 s, the flywheel). `server.py`
starts it automatically; `--no-sim` runs the server bare.

On startup it defines any of its eight entries that are missing (uids are the
table at the top of the file), so it works before a client ever connects. Use it
as the template for future systems: put your uids in a table, read inputs with
`get_switch`, write outputs with `set_gauge` on a tick.

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
