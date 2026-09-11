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
| `data/io_definitions.json` | live I/O - switch positions, indicator lamps, gauge values, annunciator windows, keyed by definition UID. Held in memory by `io_state.py`. | `GET /api/io`, `POST /api/io/*` |

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
| `annunciators` | id, legend text, tile row/column, priority, state, flashing, flash rate, acknowledged, silenced, colour, flash group, SART group |
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
                  "valid": true, "revision": 14}],
  "annunciators": [{"uid": "...", "id": "RCP_1_TRIP", "name": "RCP 1 Trip",
                    "text": "RCP 1\nTRIP", "color": "amber", "group": "MCR",
                    "sartGroup": "RCP P1",
                    "state": "alarm", "flashing": true, "flashRate": "announce",
                    "acknowledged": false, "silenced": false, "revision": 15}]
}
```

Entries are always whole, never partial, and sorted by `revision`.

`revision` is a single counter over all four collections: every change takes the
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
                "positions": ["off", "on"], "position": "on"}],
  "annunciators": [{"uid": "...", "id": "RCP_1_TRIP", "name": "RCP 1 Trip",
                    "text": "RCP 1\nTRIP", "color": "amber", "group": "MCR",
                    "sartGroup": "RCP P1"}] }
```

`id`, `name` and `positions` only matter the first time the server sees a uid
(auto-registration). The client doesn't send `powered`/`available` — it has no
opinion on those, and reporting them would clobber the server's.

**Annunciators go the other way round.** A window's uid lives in a Unity
annunciator rack definition, not here, so the server can't invent one — the
client sends the windows its racks hold, and only while the server has no
definition for them. Once registered they stop riding up and only ever come
down. It's a definition, never a state — a client has no opinion on whether an
alarm is in, and a re-registering client can't wipe a live one.

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
{ "gauges":       [{"uid": "...", "value": 47.5, "valid": true}],
  "indicators":   [{"uid": "...", "state": "red", "flashing": true}],
  "switches":     [{"uid": "...", "position": "on", "powered": true}],
  "annunciators": [{"id": "RCP_1_TRIP", "state": "alarm", "flashing": true,
                    "flashRate": "announce"}] }
```

→ `{"revision": 15, "changed": ["..."], "unknown": []}`

Annunciators take an `id` instead of a `uid` if you'd rather: a window's uid is a
GUID out of a rack definition, its id is the legend slugged (`RCP 1 / TRIP`
→ `RCP_1_TRIP`), which is the one you can type. That's also how you
acknowledge one by hand:

```bash
curl -X POST localhost:8000/api/io/set -H "Content-Type: application/json" \
  -d '{"annunciators": [{"id": "RCP_1_TRIP", "acknowledged": true}]}'
```

### `POST /api/io/save`

Writes current I/O values back to `data/io_definitions.json`.
→ `{"saved": "<path>", "revision": 15}`

## The I/O map (`data/io_definitions.json`)

Ships empty. Four collections plus config:

```json
{ "ioVersion": 1, "reportIntervalSeconds": 0.2, "autoRegisterFromClients": true,
  "switches": [], "indicators": [], "gauges": [], "annunciators": [] }
```

| Key | Effect |
| --- | --- |
| `reportIntervalSeconds` | how often the client exchanges data; sent to the client, which adopts it |
| `autoRegisterFromClients` | add switches the client reports but this file doesn't have. On by default, so the file fills itself from the scene; turn it off once the map is settled and unknown uids will be reported instead |

**Indicators are keyed by the switch's uid** — a lamp pair belongs to a switch, so
`SwitchLampIndicator` and its `Rot2p` share a UID, in different collections.

**Annunciators are keyed by the tile's uid**, which is generated in the Unity
rack definition and written into this file when a client first reports it. The
entry carries `text`, `color` and `group` alongside the state so the file reads
like the panel looks; those three are the client's and the server never writes
them. `state` is free-form — `clear`, `off` and `normal` are dark on the client
and everything else is lit — and `flashing` blinks the window in step with every
other flashing window in its rack group. `acknowledged` is bookkeeping for
whatever runs the alarm sequence; the client doesn't read it.

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
state.switches(); state.indicators(); state.gauges(); state.annunciators()

# write - each returns True if something actually changed
state.set_gauge("33bee2dd-...", 50.0)                  # the client's needle follows
state.set_indicator("a250f6ec-...", "red", flashing=True)
state.set_switch("a250f6ec-...", position="on")        # moves it for every player
state.set_switch("a250f6ec-...", powered=False)

# annunciators: find the window by the id its legend slugged into, because the
# uid belongs to a rack definition in Unity rather than to anything here
window = state.find_annunciator("RCP_1_TRIP")      # by uid or id; None if no
if window:                                             # rack in the scene has it
    state.set_annunciator(window["uid"], "alarm", flashing=True)
    state.set_annunciator(window["uid"], flashing=False, acknowledged=True)
    state.set_annunciator(window["uid"], "clear", flashing=False)

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

### The simulations

Seven working examples of the above. `server.py` starts them all automatically;
`--no-sim` runs the server bare. Each defines any of its entries that are
missing on startup (uids are in a table at the top of the file), so they work
before a client ever connects. Use them as the template for future systems: put
your uids in a table, read inputs with `get_switch`, write outputs with
`set_gauge` on a tick.

They also show how systems chain: a gauge one sim writes is the input another
reads (switches → valve position → turbine speed → the load automatic rod
control chases). No wiring needed for that — they share the one `IoState`, so a
sim just reads the uid it cares about.

**`rcp_sim.py`** — the four reactor coolant pumps, their electrical supply and
their protection. See [The RCPs](#the-rcps) below; it's the one sim with enough
in it to be worth its own section.

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

**`rod_sim.py`** — rod control, and a **temporary** reactor power model hung off
it, plus the boric acid control and the RPS trip breakers until those get files
of their own. The rod control system is the real one; the power model is the
least that behaves like a core rather than a lookup table, and it is there
because the controls on the benchboard would otherwise drive nothing. See
[Rod control and reactor power](#rod-control-and-reactor-power).

**`rcs_thermal.py`** — the primary side's temperatures: the programmed Tavg,
the core dT that comes out of power over flow, and each loop's hot and cold leg.
Server only for now; the gauges exist so the Unity faces have uids to bind to.
See [RCS temperatures](#rcs-temperatures).

### Flash rates

A flashing window blinks at one of two rates, and `flashRate` on the wire says
which. They are steps in the alarm sequence rather than decoration, so a window
usually changes rate at the same moment it changes state:

| `flashRate` | Means | Default period |
| --- | --- | --- |
| `announce` | alarm in, nobody has acknowledged it | 0.2 s lit / 0.2 s dark |
| `clear` | ringback — it cleared before anyone looked | 0.8 s lit / 0.8 s dark |

Anything else (missing, empty, a typo) reads as `announce`, so a sim that only
sets `flashing` still gets a live alarm rather than a silent ringback.

The server picks the rate; the **client owns the periods**, per rack — Flash
Seconds on the rack definition, shared by every rack in a flash group. Windows
flashing at the same rate in a group blink in step with each other and
deliberately out of step with the other rate. The horn follows one rate too
(`AnnunciatorHorn.cs`), and blips rather than holding: twice a second for
`announce`, once a second for `clear`. One horn per rack, so the sound comes
from that rack, all of them timed by the group's shared blip clock so a wide
panel still sounds like one panel. Today only `announce` has a clip, so a
ringback flashes silently until a second horn is added for `clear`.

**`ann_panel_test.py`** — **TEMPORARY.** A panel-wide flash test with no
conditions behind it: every *labeled* window that is dark is driven straight to
alarm and flashing, so a rack comes in fully alight the moment a client connects
and registers its windows. Blank cells are left alone, and so is anything
already lit — including an acknowledged window, so acknowledge still visibly
works. Re-arm by setting the windows back to `"state": "clear"`, or by
restarting the server. It cannot set the flash *rate* (that is `flashSeconds` on
the Unity rack definition, shared per flash group) and there is no audible to
sound yet. Delete the file and its two lines in `server.py` to remove it — and
this note with them.

**`annunciator_sim.py`** — the alarm windows and the SART pushbuttons, running
the sequence a real panel runs: in and flashing fast, acknowledged and steady,
and a slow ringback flash once the condition clears — whether or not anyone
acknowledged it — until somebody resets it. It's the one sim that defines
nothing on startup — a window's uid comes from the client's rack definition, so
it drives whichever of its ids have registered and skips the rest.

### SART

The four buttons are ordinary switches, read off the report every tick, acting
on the tick the button goes **down**:

| Button | Does |
| --- | --- |
| **SILENCE** | Quiet, and nothing else. Every sounding window stops feeding the horn and flashes on exactly as it was. |
| **ACKNOWLEDGE** | Seen. Every unacknowledged alarm goes steady and quiet. Clears nothing, and ignores ringbacks — reset is the ringback's acknowledge. |
| **RESET** | Every ringback out. A window still in alarm is untouched. |
| **TEST** | Held, every window on the panel reads as being in alarm, so it can be acknowledged or silenced like any other. Let go and everything that isn't genuinely in falls to ringback and waits for a RESET. |

A cluster is four switches named `<sart group> Silence` / `Acknowledge` /
`Reset` / `Test`, and it commands the windows whose `sartGroup` matches. With no
prefix — or a prefix that describes a panel rather than naming one, like
`Annunciator Ack` — it commands every window in the plant, and a window whose
rack names no `sartGroup` is reached by that master alone. They want
`Trans2pSpring` (momentary); a latching switch works but has to be flipped back
to arm the next press, and would hold the panel in test.

`sartGroup` is **not** `group`: `group` is the flash group, every rack that
blinks in step (usually a whole control room), while a SART panel commands the
one to three racks in front of it. Both belong to the client's rack definition,
and a client may re-report either on a window already registered — the server
corrects the description and never the state, so a rack can be regrouped with a
live alarm on it.

`silenced` is per window rather than per panel, which is what makes one press
quiet what is in **now** without deafening the panel to what comes next: every
transition that starts a new audible event clears the flag on the window it
happens to. The two flash rates have separate clips, so a rack wants two horns.
See `client/unbuilt/docs/server-io-sync.md` for both, and run
`python server/test_sart.py` to watch the whole sequence go past.

One window can also be driven from outside the room with `POST /api/io/set` and
`"acknowledged": true` / `"silenced": true` / `"state": "clear"`. The conditions
are thresholds on what the other sims write, so the panel has something to do
straight away:

| Window id | In when |
| --- | --- |
| `TURB_OVERSPEED` | turbine above 1900 RPM |
| `GEN_LOAD_HI` | generator above 1600 MW |
| `GRID_FREQ_ABNORM` | grid outside 59.5-60.5 Hz |
| `BYPASS_VLV_OPEN` | bypass valve past 5 % |

The RCP windows come from `rcp_sim.alarm_conditions()` rather than being listed
here — a system with a dozen of them keeps its conditions next to the state they
read, and hands `ALARMS` a block. They're in the table under
[The RCPs](#the-rcps).

`ann_panel_test.py` is a temporary lamp test that drives **every** labelled
window to alarm. It's opt-in (`--ann-test`) because it buries every real alarm
underneath it.

## The RCPs

Four Westinghouse Model 93A-class pumps (6-pole, ~7000 hp, 1190 rpm), each with
a PUMP control switch and its lamp pair, an ammeter and a loop flow gauge. The
electrical supply is modelled because it is what most of the casualties act on:

| Supply | Feeds |
| --- | --- |
| `NBUS-1` (6.9 kV) | RCP 1 and 2: **motor breaker and MCC normal supply both** |
| `NBUS-2` (6.9 kV) | RCP 3 and 4, likewise |
| `SBO-BUS-1` (480 V) | the **alternate** MCC supply for RCP 1 and 2 |
| `SBO-BUS-2` (480 V) | the alternate MCC supply for RCP 3 and 4 |

Each pump's MCC — oil lift pump, lube oil, instrumentation — sits behind a
break-before-make transfer switch that takes NORMAL when its NBUS is live and
ALTERNATE when it isn't. **No MCC means no pump**: a pump whose auxiliaries have
neither supply is tripped.

### The control switch

Each pump answers to a spring-return **TRIP / NORMAL / START** controller
(`Rot3pSpring`). Both ends are momentary and the switch lives in the middle; it
reports geometry rather than meaning, so on the wire the positions are:

| Position | Wire name | Does |
| --- | --- | --- |
| TRIP | `left` | opens FDR-52. Latches nothing — only protection drives a lockout |
| NORMAL | `center` | rest. The spring returns here on its own |
| START | `right` | closes FDR-52 if the start permissives hold, otherwise refuses **with a reason** on the console |

**Only the move onto an end is a command.** The server reads edges, not levels:
one press sits on an end for several ticks, and acting on the level would
re-close the breaker on every one of them — and would close it the moment a
permissive came back with the operator's hand still on START.

Panel behaviour on a trip: the breaker opens, the green lamp lights to say so,
the **run light** goes out, and the switch is already back at NORMAL — the lamps
are the only breaker indication there is. Nothing restarts the pump by itself;
the operator clears the casualty, runs `tripreset`, and presses START. A
maintained switch needed the out-of-correspondence rule from
`misc/systems/rcs/rcp.json` to get that guarantee, so with this controller that
rule is gone.

**A trip will not reset onto a live casualty.** `tripreset` is refused, with the
reason, while any condition that would raise the trip again is still standing:

| Sealed in by | While |
| --- | --- |
| bus undervoltage | the pump's NBUS is dead |
| MCC power loss | the MCC has **neither** supply (main power loss alone doesn't count — the alternate carries it, and the pump doesn't trip on it either) |

Clear the casualty and reset again. What is deliberately **not** in that list is
anything only true *because* the pump is tripped: a feeder ground fault trip
makes its own MCC normal supply unavailable, and counting that would seal the
lockout in against itself with no way out.

Nor is an MCC ground fault (`rcp-n-mcc-gft`). 50G at the LV main trips MCC-52
and stops there — selectivity, and the motor sits in another zone behind
FDR-52 — so it never reaches the motor's protection and has no trip to seal
in. The pump runs straight through it on the alternate feed with `MCC MAIN
POWER LOSS` and `MCC/FDR Ground Fault` both in. Only losing **both** MCC feeds
blocks a reset, and the MCC power loss row above already covers that.
`python server/test_rcp_trip.py` walks the whole interlock.

Two lamps per pump, both `SwitchLampIndicator`:

| Lamp | uid | Shows |
| --- | --- | --- |
| the switch's pair | the switch's own uid | red closed / green open. The switch is back at NORMAL either way, so this pair **is** the breaker indication |
| the run light | its own definition's uid | lit while the breaker is closed, dark otherwise. One lamp, so it has no "stopped" colour |

The run light hangs under no switch, so it carries a `SwitchDefinition` of its
own — `RCP n Run Lamp` under `Controls/Definitions/RCS Section`, assigned to the
lamp's prefab instance in `MainScene`. The uids are in the `PUMPS` table in
`rcp_sim.py` as `runlamp`, alongside the switch and gauge uids.

It used to answer to its own GameObject's name instead, via the fallback in
`SwitchLampIndicator.Id` for a lamp with neither a definition nor a switch above
it. That bound the wire protocol to a name in the scene hierarchy, so renaming
the object in the editor silently unbound the lamp. The fallback is still there
for lamps that genuinely have no definition.

| Window id | In when |
| --- | --- |
| `NBUS_1_POWER_LOSS`, `NBUS_2_POWER_LOSS` | that NBUS is de-energized |
| `RCP_n_TRIP` | the pump is tripped, for any reason |
| `RCP_n_FDR_MECH_RELAY_TRIP` | tripped by feeder protection — `tripfdrmech`, or bus undervoltage |
| `RCP_n_MCC_FDR_GROUND_FAULT` | `tripfdrgft`, or the `rcp-n-mcc-gft` fault |
| `RCP_n_LUBE_SYSTEM_TROUBLE` | tripped by `triplst` |
| `RCP_n_MCC_MAIN_POWER_LOSS` | the MCC's normal (NBUS) supply is unavailable |
| `RCP_n_MCC_AUX_POWER_LOSS` | the MCC's alternate (SBO bus) supply is unavailable |

## Rod control and reactor power

**Temporary, and knowingly so.** Two controls went onto the MRCS section of the
benchboard — a ten-detent **Rod Bank Selector** (`RotNp`) and a spring-return
**Rod Control Lever** (`Rot3pSpring`) — and until there is a secondary plant, a
Tavg program, boron and nuclear instrumentation to control against, the only
thing they can drive is a stand-in. So `rod_sim.py` splits in two: the
Westinghouse rod control *system*, which is cheap to get right and is right, and
the smallest reactivity-to-power model that behaves like a core. The second half
is the part to delete when the real systems land.

### The MRCS section

Three controls and ten meters, all under `Controls/Definitions/MRCS Section`.

| Signal | Uid | Positions / range | Direction |
| --- | --- | --- | --- |
| Rod Bank Selector | `0a796bbb` | `p1` … `p10` | in |
| Rod Control Lever | `e6c75ffc` | `left` / `center` / `right` | in |
| Fast Withdraw | `f1f6859a` | `off` / `on` | in |
| APRM | `7ac28af5` | 0–120 % | out |
| Period | `15001ded` | −180 … +180 s | out |
| SA … SD Bank Position | `d5e5e3d3`, `214974d1`, `f3f13f45`, `8bb25c98` | 0–228 steps | out |
| A … D Bank Position | `f150eb78`, `6c9e5419`, `54b74a88`, `87d21520` | 0–228 steps | out |

The selector and the lever are read as **levels**. The lever is the one control here that is
not read as an edge, which is the opposite of the RCP control switch: holding it
is not one command but a train of them, and rods step at the programmed speed
the whole time. The one edge that matters is the first — a magnetic jack has no
move smaller than a whole step, so however brief the bump, the selected bank
moves once.

Every uid here was generated **on the server** rather than in Unity, because
each of these went into the scene as a placeholder with nothing assigned — the
two switches with no `SwitchDefinition` at all, and all nine gauges pointing at
the one `APRM` definition, which had no uid generated into it. `IoSync` skips a
control with no definition and a definition with no uid, so none of it synced.
The definition assets now carry these ids, one per signal.

> **Fast Withdraw needs a controller before it does anything in the room.**
> The definition exists and the server reads it, so `/turnswitch Fast Withdraw
> on` works today — but the instance in the scene is a bare model with a
> nameplate and no switch handler on it, and `IoSync` has nothing to report.
> Add a `Rot2p` to the model root, drag the moving part onto **Handle** and
> `Fast Withdraw` onto **Definition**, per *Adding an interactable* in
> `docs/interactable-api-usage-guide.md`. Its lamp pair needs nothing: a
> `SwitchLampIndicator` under a `Rot2p` mirrors it locally, and no indicator is
> defined server-side, so the server never takes the lamps off it.

> The eight `* Bank Position` definitions were written with no baked face, so
> their needles read correctly but the printed dials are still wearing
> `APRM_Face.mat`. All eight are configured identically (0–228 steps, majors at
> the quarters of full travel, empty `displayName` — the bank nameplate is a
> separate TMP object in the gauge prefab), so **one** bake serves all eight
> faces: select them, hit *Bake Dial Face*, and put the material it makes on
> each face renderer.

**The bank meters are a stand-in.** A real plant reads bank position two other
ways as well, and the client has a controller for neither: the group demand
**step counters**, which are digital readouts, and **DRPI**, which reads each
rod individually off its CRDM coil stack. An analog bank position meter is a
real thing to have on the board, but it isn't the whole picture — and
everything else the model knows (the reactivity balance, startup rate, which
rod stop is standing) has no panel indication at all and lives on the console
under `/rods`.

### What each detent selects

`RotNp` reports geometry, not meaning, so `p1`…`p10` mean what this table says
and nothing on the client knows it. The dial is laid out the way the real
switch is: the four shutdown banks at one end, the four control banks at the
other, and MAN and AUTO in the middle — which is where the switch stands for
the whole run, with the startup banks behind it and the at-power banks ahead.

| Detent | Selects | Moves |
| --- | --- | --- |
| `p1`–`p4` | SA, SB, SC, SD | that shutdown bank, alone |
| `p5` | **MAN** | control banks A–D, in the overlap sequence |
| `p6` | **AUTO** | control banks A–D; automatic control has the jacks and the lever is bypassed |
| `p7`–`p10` | CA, CB, CC, CD | that control bank alone, defeating the sequence |

The switch starts on `p1` (SA), the first bank withdrawn on the way up — which
has to agree with **Default Position** on the `RotNp` in the scene, because the
client reports its own detent over the server's on the first sync.
`test_rod_control.py` checks that the two still agree, and that the scene has as
many detents as this table does.

The server settles the ten detents itself on startup rather than letting the
client auto-register them, because the server takes a switch's position list
**once**: a client that got there first with a different count would leave
reports of the detents past that being dropped as positions it has never heard
of.

### The banks

Eight banks, 53 rod cluster control assemblies between them, 228 steps of travel
each on a 5/8 in magnetic-jack step — so full travel is the 12 ft core. Position
is *steps withdrawn*: 0 is on the bottom, 228 is fully out.

| | Banks | Worth (pcm, approx) | Moves |
| --- | --- | --- | --- |
| Shutdown | SA, SB, SC, SD | 1100 each | only on its own detent — MAN and AUTO never touch them |
| Control | CA, CB, CC, CD | 350 / 450 / 700 / 850 | in sequence under MAN and AUTO, or alone on its own detent |

Manual rod speed is a fixed **48 steps/min** (30 in/min). The automatic
controller has a speed program between **8 and 72 steps/min** (72 is 45 in/min),
proportional to how far off it is.

**Fast withdraw.** Every bank from the bottom is 912 steps of shutdown bank and
612 of control bank demand — a bit over half an hour at 48 steps/min, which is
right for the operator it's modelled on and useless for testing. Boration is the
same problem from the other end: holding rated power with the rods out wants
4.4 % of boric acid, three quarters of a minute of holding a switch to reach and
the same again to undo.

The switch multiplies **every control an operator holds** — the rod lever and
the [boric acid control](#cvcs--the-boric-acid-control) — by 20, so that startup
is about ninety seconds. Both by the **same** factor, deliberately: their
authority relative to each other doesn't change, so the reactivity balance is
still worked the same way rather than becoming a race between a fast lever and a
slow shim.

It touches nothing automatic. The controller's 8–72 steps/min is a real design
parameter and scaling it would break the modelled behaviour rather than hurry it
along, and rod drop is 2.2 s already — gravity was never the slow part. The
console says so loudly whenever the switch goes in, because it is a test aid and
not a plant control.

One thing to know about using it: pulling every bank out cold at 20× puts
**+1600 pcm** in the core, far past prompt critical, and the one-group period
has no meaning up there — the `SUR_MAX_DPM` clamp is what stops the exponent
running away, and power then climbs at a capped 5 DPM until the power defect
catches it at 100 %. So the end state is right and the transient in between
isn't physics. Withdrawing at the real rate keeps rho inside a few hundred pcm
the whole way, which is where the model is honest.

**The overlap sequence.** Under MAN and AUTO the next control bank starts out
when the one before it reaches **128 steps**, so the two of them step together
over that bank's last 100 steps and there are never three in motion at once.
Insertion runs the same sequence backwards: the two banks that came out together
go back in together. The sequence is read off the bank positions rather than off
a group demand counter, so a bank moved out of sequence on its own detent
doesn't leave the sequencer confused about where it is.

### Rod stops

Withdrawal only. Rods going in is the safe direction and nothing blocks it.

| Stop | Blocks | While |
| --- | --- | --- |
| shutdown bank permissive | control bank withdrawal | any shutdown bank is not fully out |
| **C-2** | all withdrawal, manual and automatic | power range flux at or above 103 % |
| **C-5** | *automatic* withdrawal only | turbine load below 15 % — the operator's lever is unaffected, which is how the plant gets up to load in the first place |

### The power model

A reactivity balance and a period, which is the least that behaves like a
reactor:

```
rho = core excess - worth still inserted - boron - power defect x power
```

Withdrawing a bank recovers its worth on the usual S-curve — differential worth
is `1 - cos(2 pi x)`, zero at both ends where the flux is low and greatest at
mid-core. Power feeds back through the **power defect** (1600 pcm, hot zero
power to hot full power), so rho falls as power rises and the core settles
instead of running: 16 pcm of rods is about 1 % of power.

**Core excess is pinned to `ARO_POWER_PCT`, which is 122 %.** All rods out at
the nominal boron concentration therefore asks for *more* than rated — a core
with every rod out and nothing else holding it down is not sitting politely on
100 %, and boron is what brings it back. That is the whole reason chemical shim
exists, and it is why the boric acid control has a job.

Two consequences worth knowing, both of which `test_rod_control.py` pins:

- **You cannot actually reach all-rods-out by holding the lever.** The banks
  ask for more than rated on the way, so power crosses 103 % and the **C-2 rod
  stop blocks the withdrawal** with a control bank still part way out. The
  interlock beats the operator, which is what it is for. The ways past it are to
  borate first, or to cheat with `Fast Withdraw`, which outruns the power rise —
  and then you trip on high flux at 118 % instead.
- **Borating 4.4 % above nominal holds exactly 100 %** with the rods out, which
  is the normal at-power configuration.

Power then follows the period, the way an operator reads it: startup rate in
decades per minute, one delayed group (beta 0.0065, lambda 0.1 /s),
`SUR = 26.06 / period`, and `P x 10^(SUR x dt / 60)`. +100 pcm is a 55 s period
and about half a decade a minute. Negative rho decays power, floored at
**-1/3 DPM** — that floor is the real limit set by the longest-lived delayed
group, not a fudge. Rod worth is what makes any of this slow: 48 steps/min
against 7.5 pcm a step is ~6 pcm/s, so a continuous pull is 20-odd %/min of
power and not a step change.

Two clamps aren't physics. Power floors at 1e-8 % standing in for source
neutrons (subcritical multiplication isn't modelled), and SUR ceilings at
+5 DPM because above prompt critical a one-group period means nothing.

**The period meter** is the inverse of that startup rate, in seconds, signed by
which way power is going. Read it the way you read the RCP ammeter — off its
stop: period runs to infinity as the core settles, so a **steady reactor pegs
the needle at an end** and comes off it as reactivity appears. −78 s is the
fastest it can read going down (that's the −1/3 DPM floor) and +5.2 s the
fastest going up (the +5 DPM clamp).

> The dial is linear in seconds with **0 at the centre**, which means both ends
> mean "steady" and the needle crosses the whole face when the sign flips. Real
> period meters avoid that by putting infinity at the *centre* and labelling a
> reciprocal scale (±10, ±30, ±100, ∞) — deflection then goes as 1/τ, which is
> the startup rate. If `Period.asset` is ever re-baked that way, publish
> `DECADES_PER_MINUTE / period` instead; it's one line in `_publish`.

**AUTO** chases the turbine's load — `Gen Load` over the machine's rating —
because holding Tavg on program is what that amounts to, and there is no Tavg
yet. Deadband ±1 %, standing in for the real ±1.5 °F of Tavg error.

### The trip

Two trip breakers, RTA and RTB, in series in the rod drive supply — see
[RPS](#rps--the-trip-breakers) for the pushbuttons that work them. Either one
open drops every bank to the bottom in 2.2 s and blocks withdrawal while it is
open.

One automatic function opens both: **power range neutron flux high at 118 %**.
It stands in for `RPS`, which is a system of its own and isn't written, and it
is here because a power model with no trip just sits against its ceiling. A
breaker will not close while flux is still at or above the setpoint — the same
sealed-in rule the RCP lockouts follow. `/rods trip` and `/rods reset` work both
trains at once from the console.

| Window id | In when |
| --- | --- |
| `RX_TRIP` | the reactor is tripped |
| `PWR_RANGE_HI_FLUX` | power at or above 103 % |
| `ROD_STOP` | any rod stop is standing |

No rack in the scene carries these yet, which is fine — `ALARMS` skips the ids
no rack registered.

### What this is not

Boron is here, but only as a deviation from nominal, on a percentage rather than
in ppm, and moving far faster than a charging path could shift a concentration.
There is no xenon, no decay heat and no source range instrumentation. Tavg
exists now (`rcs_thermal.py`) but nothing reads it back: **the causality is
still backwards** from a real PWR at power, where steam demand sets power and
the rods only trim Tavg. Here rod position sets power, because nothing else is
there to set it. AUTO papers over that by chasing turbine load, and that is the
first piece to delete when the secondary plant lands.

`python server/test_rod_control.py` walks the sequence, the rod stops, the
reactivity balance and the trip.

### CVCS — the boric acid control

**Temporary, and living in `rod_sim.py` because that is where the reactivity
balance is.** One switch and one meter under `Controls/Definitions/CVCS Section`,
and the whole of chemical shim as far as this code is concerned.

| Signal | Uid | Positions / range | Direction |
| --- | --- | --- | --- |
| Boric Acid Control | `02d05332` | `left` / `center` / `right` | in |
| Boric Acid | `47c04141` | 0–100 % | out |

Right borates and left dilutes, so right raises the reading — the same way right
opens a valve and right withdraws a rod. Read as a **level**, like the rod
lever: it moves for as long as it is held.

Only the **deviation from nominal** carries reactivity, at 80 pcm per percent.
Nominal (50 %) is already inside the core excess, so it contributes nothing —
which is what makes that number mean "all rods out at the normal concentration".
Borate above nominal and the core comes down; dilute below it and it goes up,
by 4000 pcm at either end of the meter.

Real chemical shim is a concentration in ppm worth about −10 pcm/ppm, moved
through the charging path over tens of minutes. This is a percentage, and it
moves 20-odd times faster than a charging pump could shift it — deliberately, so
the switch has about the same authority as the rod lever and is usable. When
CVCS lands as its own system it takes all of this with it.

**`Fast Withdraw` multiplies this too**, by the same 20 as the rod lever, which
is what keeps those two authorities matched with the switch either way. So the
4.4 % that holds rated power is a couple of seconds of holding rather than
three quarters of a minute — see
[fast withdraw](#rod-control-and-reactor-power).

### RPS — the trip breakers

Also temporary, also in `rod_sim.py`: these are the last two inches of a system
with a couple of dozen inputs, and the rest of it isn't written. Four
pushbuttons under `Controls/Definitions/RPS Section`.

| Signal | Uid | Positions | Direction |
| --- | --- | --- | --- |
| RPS A Trip | `bcc2377b` | `released` / `pressed` | in |
| RPS B Trip | `f0541f68` | `released` / `pressed` | in |
| RPS A Close | `a05647e9` | `released` / `pressed` | in |
| RPS B Close | `63388349` | `released` / `pressed` | in |

RTA and RTB sit in **series** in the rod drive supply, so **either one open
drops every rod**. Each train has its own trip and its own reset, and one
automatic function — power range flux high — opens both.

Unlike the rod lever these are read as **edges**: a pushbutton is one command
however long a thumb sits on it, so holding the trip button down does not stop
the breaker being closed again. A breaker will not close while flux is still at
or above the setpoint — the same sealed-in rule the RCP lockouts follow.

> **The reset buttons are called CLOSE, and must not be called Reset.**
> `annunciator_sim.py` classifies SART buttons off the tail of a switch's name:
> anything ending in `Reset` reads as an alarm reset, and a cluster whose group
> matches no rack falls back to commanding **every window on the plant**. So
> `RPS A Reset` would have cleared every ringback in the control room the first
> time anyone pressed it. Close is also the right word — resetting a reactor
> trip *is* closing the trip breaker. Rename these to anything that doesn't end
> in acknowledge / ack / silence / reset / test.

Note one divergence from the real thing: a Westinghouse manual trip is two
pushbuttons **either** of which de-energizes **both** trains. Per-train is what
the four buttons on this panel are for, and the series breakers make the
outcome the same — one press still drops every rod.

## RCS temperatures

`rcs_thermal.py`. Server only, and nothing displays it yet: the ten gauges are
defined so the uids exist for the Unity faces when they get baked. Everything
downstream of the primary will read these — the subcooling margin monitor, the
SG secondary side, the low-flow and OTΔT/OPΔT trips, and the Tavg program the
automatic rod controller is currently faking with turbine load.

| Signal | Uid | Range | Direction |
| --- | --- | --- | --- |
| RCS Tavg | `2da5252a` | 500–700 °F | out |
| Core dT | `155edff7` | 0–150 °F | out |
| Loop 1–4 Th | `13fe2e1c`, `9e8647dc`, `27b50ac6`, `bc10d2dd` | 500–700 °F | out |
| Loop 1–4 Tc | `c301b2a9`, `86a37369`, `13eb0f17`, `586678e0` | 500–700 °F | out |

### Power over flow

The one relationship that matters. Core power lands in the coolant, and how much
the coolant warms up crossing the core is that power divided by the mass flow
carrying it away:

```
dT = 61 F x (power / rated) / (flow / rated flow)
```

So **ΔT is not a property of power alone**. At rated power on four pumps it is
61 °F. Lose two pumps and the same power has half the flow to carry it, so ΔT
doubles to 122 °F — which is why full power on two loops is not a thing anyone
does, and why the low-flow trip exists. Losing flow pushes Th up and Tc down
around a Tavg that hasn't moved.

Flow comes straight off `rcp_sim`'s four pumps, so it follows the flywheels: trip
a pump and ΔT climbs over the coastdown rather than stepping. Rated total flow is
four times whatever `rcp_sim` rates one pump at, so retuning the pump moves this
with it instead of leaving two numbers to drift apart.

### Where Tavg comes from

It is **programmed**, not derived. A Westinghouse plant holds Tavg on a straight
line against load — 557 °F at no load to 587.5 °F at full power — and the rods
are what hold it there. The two ends are the same number twice over: **no-load
Tavg is exactly full-power Tc**, which is what makes the reference numbers in
`misc/systems/rcs/loop.json` come out at Th 618 / Tc 557 by construction rather
than by tuning. `test_rcs_thermal.py` checks them against that file.

Here the program is driven off reactor **power** rather than turbine load,
because `rod_sim` currently makes power the independent variable. When the
secondary plant lands this inverts: steam demand sets load, the program sets
Tavg from load, and the rods chase it.

Tavg follows its program through a 90 s lag, because a couple of hundred tonnes
of water and steel do not change temperature the instant the flux does. ΔT is not
lagged — it is a ratio of two things that are themselves already slow.

### The legs

All four hot legs carry the same Th: the core outlet is one mixed plenum. All
four cold legs carry the same Tc when every loop is running.

A loop whose pump is stopped is the exception, and it does something people find
surprising: **its flow reverses**. The running pumps push water out of the vessel
through the idle loop's cold leg, backwards through its pump and steam generator,
and back into the vessel through its hot leg. So that loop's legs **both read
about Tc**, its steam generator is being back-fed and removes essentially
nothing, and none of it shows up as core ΔT. With every pump stopped there is no
reverse flow to have — natural circulation is forward — so the whole plant falls
back to a flow floor of 4 % of rated, which is what stops ΔT going to infinity
when the flow term goes to zero.

`/rcs` prints all of it, and flags which loops have reversed.

## The server console

`server.py` reads commands off stdin while it serves; `commands.py` routes them.
These are an instructor's console, not an operator's — the things that happen
*to* a plant, which have no control in the control room. The leading slash is
optional, and names ignore case, spaces, hyphens and underscores, so
`RCP 1 Power` and `rcp-1-power` are the same switch.

| Command | Does |
| --- | --- |
| `/turnswitch <switch> <position>` | move any switch server-side. Position by name (`on`, `left`) or 1-based number, so `pos1/2/3` on a three-way |
| `/fault add\|clear <fault>` | insert or clear a casualty |
| `/fault clearall` | clear every fault |
| `/component <name> <action>` | act on one component |
| `/status` | bus, MCC, breaker, speed and trip state for all four RCPs |
| `/rods` | bank positions, the reactivity balance, startup rate and reactor power |
| `/rods trip\|reset` | trip the reactor, or reset both trains |
| `/rcs` | Tavg and its programme, core dT, and Th/Tc for every loop |
| `/help [command]` | the list, or detail on one |
| `e` | stop the server |

Faults (`/help fault` prints this list, generated from the sim):

| Fault | Does |
| --- | --- |
| `nbus-1-trip`, `nbus-2-trip` | de-energize that NBUS: motors trip on undervoltage and the MCCs transfer to alternate |
| `sbo-bus-1-trip`, `sbo-bus-2-trip` | de-energize that SBO bus: no alternate MCC supply left |
| `rcp-n-mcc-mpl` | MCC main power loss — transfers to alternate, and trips the pump if there isn't one |
| `rcp-n-mcc-gft` | as `mpl`, plus the red `MCC/FDR Ground Fault` window |

Actions on `rcp-1` … `rcp-4`:

| Action | Does |
| --- | --- |
| `trip` | trip the pump, no reason given |
| `tripreset` | reset the trip; refused while a casualty still seals it in. Does not restart the pump — press START |
| `tripfdrgft` | feeder ground fault: trips the pump and swings the MCC to alternate |
| `tripfdrmech` | feeder electrical/mechanical protection trip (undervoltage, overspeed) |
| `triplst` | lube system trouble trip |

```
> /turnswitch RCP 1 Power right
RCP 1 Power: center -> right
> /fault add nbus-1-trip
inserted nbus-1-trip - NBUS-1 de-energized (feeder + MCC main for RCP 1 and 2)
> /component rcp-1 tripreset
RCP 1 trip will not reset - bus undervoltage. The lockout is sealed in while the
condition is there; clear it and reset again.
> /fault clear nbus-1-trip
cleared nbus-1-trip
> /component rcp-1 tripreset
RCP 1 trip reset - START to restart
> /turnswitch RCP 1 Power right
RCP 1 Power: center -> right
```

The MRCS section shows reactor power and the eight bank positions, but not the
reactivity balance behind them, so `/rods` is the only place to read why the
needles are going where they are:

```
> /turnswitch Rod Bank Selector 6
Rod Bank Selector: p1 -> p6
> /rods
Rod control:
  selector  AUTO (p6 )    lever  HOLD    fast withdraw  out

  bank        SA    SB    SC    SD    CA    CB    CC    CD
  steps      228   228   228   228   228   228   228   153
  worth     1100  1100  1100  1100   350   450   700   850

  core excess         +1600 pcm
  rods inserted        -161 pcm
  power defect        -1439 pcm
  net reactivity         +0 pcm

  startup rate        +0.00 dpm
  period               +180 s  (off scale - nothing much is happening)
  reactor power      89.960 %   (3249 MWt)

  reactor not tripped
  rod stop: none
> /rods trip
reactor tripped - operator trip; every bank to the bottom
```

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
