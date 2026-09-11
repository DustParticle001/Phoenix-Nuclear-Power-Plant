# Live I/O sync (switches, indicators, gauges)

`IoSync` keeps the scene and the server in step on a timer. One request per tick
does both directions:

| Direction | What moves |
| --- | --- |
| up | the position of **every** switch definition in the loaded scene, plus any annunciator windows the server hasn't registered yet |
| down | switches other players moved, indicator lamp states, gauge values, annunciator windows |

Everything is matched by **definition UID** — `SwitchDefinition.Id` for switches
and indicators, `GaugeDefinition.Id` for gauges, the tile uid for annunciator
windows. Nothing depends on object names or hierarchy, and a control with no
definition assigned is skipped (it has no UID the server could key on).

Nothing needs wiring in a scene: `IoSync` lives on the `ServerConnection` object
the join screen creates, which survives scene loads. After every scene load it
re-scans the scene and pulls the full state again.

## The tick

1. **On connect / after a scene load** — `GET /api/io` for the whole map, applied
   to the scene. New controls start at their scene defaults, so the client pulls
   before it ever reports, rather than reporting defaults over live state.
2. **Every `reportIntervalSeconds`** (the server states it; 0.2 s by default) —
   `POST /api/io/report` with every switch position, and the response carries
   everything this client hasn't seen: other players' switches, indicators, gauges.
3. **Applying** — a switch is only moved if it isn't already where the server says
   (`SetPosition` animates and logs), gauges go through `GaugeNeedle.SetValue`,
   indicators through `SwitchLampIndicator.SetServerState`, annunciator windows
   through `AnnunciatorTile.SetServerState`.

Timing uses real time, so sync keeps running if the simulation pauses time.

If the server restarts, its `sessionId` changes and the client resyncs from
scratch — revisions start over on the server, so a diff against an old revision
would be meaningless.

## Two players, one switch

Clients report every switch every tick, so a client with a stale view would
otherwise keep reasserting it. The server only accepts a reported change from a
client that had already seen that switch's current value; otherwise it rejects it
and returns the current value in the same response, and the client corrects itself
on the next frame. Within one interval, the last accepted write wins.

## Adding controls

Nothing to register. Give the control a definition with a UID and it syncs:

- **Switches** — any handler implementing `ISwitchControl` (`Rot2p`, `Rot3p`,
  `RotNp`, `Rot2pSpring`, `Rot3pSpring`, `Trans2p`, `Trans2pSpring`). Positions
  are the names on the wire: `off`/`on` for the two-position rotaries,
  `left`/`center`/`right` for the three-position ones, `p1`…`pN` for a
  multiposition selector, `released`/`pressed` for the pushbuttons. A
  spring-return handler reports the same names as its latching counterpart, so
  which one a definition is on is the client's business and not the server's.

  **Settle a `RotNp`'s detent count before the server first sees it.** The
  server takes a switch's position list once, when it registers the uid, and
  only the position comes up after that — so a switch that grew from four
  detents to six leaves the server knowing four, and reports of `p5` are
  dropped as a position it has never heard of. Either fix the count first, let
  the sim define the switch itself (`rod_sim.py` does, for exactly this
  reason), or delete that switch from `server/data/io_definitions.json` and let
  it register again.
  Unlike gauges, a switch is one-to-one: two controls reporting one UID would
  fight over it, and `IoSync` warns and keeps the first.

  **Spring-return controls and the tick.** `Rot2pSpring`, `Rot3pSpring` and
  `Trans2pSpring` are off their rest position only while the player holds the
  mouse button, and reports go out on a timer — so a quick tap could fall
  between two reports and never be seen. Each of them therefore holds its
  position for a **minimum** time (`Minimum Hold Seconds`, 0.25 s) before
  springing back, which guarantees at least one report carries the press. Set it
  at or above `reportIntervalSeconds` if the server asks for a slower rate than
  the 0.2 s default.

  While the button is down the control **ignores** positions coming down for it:
  the server holds the old value for the tick between the press and the report
  being accepted, and the operator's hand is the better authority for that tick.
  The press still needs a sim that reads it as an *edge* — the wire carries a
  position, so a momentary command shows up as one or more ticks at `pressed`
  followed by a return to `released`, not as an event.
- **Gauges** — any `GaugeNeedle`. Note that `Use Test Value` on the needle
  overrides server values; turn it off for gauges the server drives.
  Several needles **may** share one UID — one signal, more than one face. The
  turbine tachometer does this: a 0–2000 RPM dial and an expanded 1795–1805 one
  for synchronising, both fed the same value, each clipping it to its own
  definition's range. Same trick works for a repeater on a second panel.
  A definition whose sweep is the full circle (`startAngle` 0 → `endAngle` 360,
  like the synchroscope) is treated as wrapping: the needle takes the short way
  between two readings, so a pointer turning past 12 o'clock carries on round
  instead of unwinding all the way back.
- **Indicators** — any `SwitchLampIndicator`. It answers to its own `Definition`
  if one is set, then the UID of the switch it hangs under, and failing both to
  its own **object's name**. That last one is for a lamp that is nobody's pair
  — a pump run light standing on the panel — which would otherwise have no uid
  and be skipped in silence. The name is a real uid on the server, so renaming
  the object renames it there: give it a definition if you want a name that
  survives being renamed.
- **Annunciator windows** — any `AnnunciatorTile`, built into a rack by
  `AnnunciatorRackBuilder` from an `AnnunciatorRackDefinition`. Several windows
  **may** share a uid, like gauges: the same alarm repeated on a second rack is
  a repeater, and both light.

With `autoRegisterFromClients` on (the default), switches the server doesn't know
about are added to `data/io_definitions.json` on the first report, using the
definition's asset name and display name — so the file fills itself from the
scene instead of being typed out by hand. Watch the server console for
`[io] registered switch ...` lines.

## Annunciator windows

Windows are the one thing in the map the **client** defines. A window's uid lives
in the Unity rack definition (generated when its CSV was imported), so the server
can't invent one — a uid it made up would answer to no rack. Instead the client
reports the windows its racks hold, and only while the server has no definition
for them:

1. A full sync returns the whole map, so any window in the scene that isn't in it
   is one the server doesn't have.
2. Those ride up with the next report — uid, id, legend, lens colour, flash
   group — and the server writes them into `data/io_definitions.json`.
3. It answers with them in `registered`, and they stop being sent. A rack is
   dozens of windows and the report goes out several times a second, so steady
   state carries none of this.

A window's **grouping** is the exception to that: `group` and `sartGroup` belong
to the rack definition, so the copy the server took when the window registered
goes stale the moment a rack is renamed or moved to another SART panel. The
client compares the two on every full sync and re-reports whatever disagrees;
the server corrects the description and nothing else, so a window in alarm stays
in alarm through the move. Steady state carries none of this, exactly like
registration.

Nothing else about a window ever comes up again: it's a definition, never a state.
Coming down, only `state`, `flashing`, `flashRate` and `silenced` are read — the
lens colour belongs to the physical window, not to the server.

`state` is free-form. `clear`, `off`, `normal`, `reset` and empty read as dark;
**everything else lights the window**, so a server can name states (`alarm`,
`cleared-unacked`, whatever comes next) without the client having to keep up.

The readable id is the legend, slugged: `RCP 1 / TRIP` → `RCP_1_TRIP`.
That's what a simulation addresses a window by, because the uid is a GUID nobody
wants to type. Give the CSV an `id` column to name them yourself.

## SART — silence, acknowledge, reset, test

The alarm **sequence** is the server's (`annunciator_sim.py`); the flash and the
horn are the client's. What passes between them is four fields per window:
`state`, `flashing`, `flashRate` and `silenced`.

| The window is | `state` | `flashing` | `flashRate` | lamp | horn |
| --- | --- | --- | --- | --- | --- |
| dark | `clear` | false | — | out | silent |
| in, unacknowledged | `alarm` | true | `announce` | fast flash | alarm horn |
| in, acknowledged | `alarm` | false | — | steady lit | silent |
| over, not reset | `cleared-unacked` | true | `clear` | slow flash | ringback |
| silenced, either way | unchanged | true | unchanged | still flashing | silent |

A window reaches ringback whether or not anyone acknowledged the alarm: "it
happened, and it is over" is worth a look even if somebody saw it come in. Only
**RESET** takes it dark from there — acknowledge is for the alarm, reset is the
ringback's acknowledge.

### The four buttons

They are ordinary switches, synced like any other, and the server reads them off
the same report every tick:

| Button | Does |
| --- | --- |
| **SILENCE** | Quiet, and nothing else. Every sounding window stops feeding the horn and flashes on exactly as it was. |
| **ACKNOWLEDGE** | Seen. Every unacknowledged alarm goes steady and quiet. Clears nothing; ignores ringbacks. |
| **RESET** | Every ringback out. A window still in alarm is untouched. |
| **TEST** | Held, every window on the panel reads as in alarm — fast flash, sounding, ackable. Let go and everything that isn't genuinely in falls to ringback and waits for a RESET. |

They want `Trans2pSpring` (momentary — a latching switch would hold the panel in
test), and they fire on the tick the button goes **down**: holding one acts once.

### Which windows a cluster commands

The server reads it off the switch **names**: a cluster is four switches called
`<panel> Silence`, `<panel> Acknowledge`, `<panel> Reset`, `<panel> Test`. What
comes before the action word is the **SART group** it commands — the `sartGroup`
its windows carry. Spelling is loose: `RCP P1`, `RCP_P1` and `rcp-p1` are one
name.

**`sartGroup` is not `group`.** A window carries both, and they partition the
same racks differently:

| Field | Groups | Scope |
| --- | --- | --- |
| `group` | racks that blink and sound **in step** | usually a whole control room |
| `sartGroup` | racks **one SART panel commands** | the one to three racks in front of it |

A control room flashes as one panel because that is what an operator sees from
across it; a SART cluster works the racks within reach. One name for both would
tie the panel you can reach to the panel you can see.

Leave the prefix off — or make it a word that describes a panel rather than
naming one (`Annunciator Ack`, `Alarm Reset`) — and the cluster commands **every
window in the plant**, whatever group they are in: a master cluster. A window
whose rack names no `sartGroup` is reached by the master **alone**. A prefix
matching no rack's `sartGroup` commands everything too, and says so once in the
console, so a half-configured panel still works while you wire it up.

On the client those names come from **`SartPanel`**, one component on the panel
root with one field: the SART group. It finds the four buttons by GameObject name
and names them from the group, so the buttons need no definition assets and a
panel is a prefab you stamp out. Nothing to register on either side — set the
group on the racks and on the panel, and it works. See
`docs/interactable-api-usage-guide.md`.

The buttons stay ordinary switches, one uid each, so they sync and arbitrate
like any other control — which is what lets one operator watch another press
them.

### Silence is per window, not per panel

`silenced` rides on the window rather than on the panel, which is what makes one
press quiet what is in **now** without deafening the panel to what comes next.
Every transition that starts a new audible event — a new alarm, a condition
clearing into ringback — clears the flag on the window it happens to. So:
silence the panel, and the next alarm still sounds while the ones you silenced
stay quiet.

On the client this is a second count on each flash clock
(`AnnunciatorFlashGroups`): every flashing window counts towards the **lamps**,
and only an un-silenced one counts towards the **horns**. The horn reads the
audible count, so silencing is a lamp-untouched mute, and the count leaving zero
resyncs the blip clock — which is why a new alarm sounds the instant it lands
rather than up to a blip interval later.

### The two sounds

The two rates have separate clips, because the ear has to tell them apart from
across the room without reading a legend:

| Clip | Rate | What it is |
| --- | --- | --- |
| `Assets/Audio/AnnunciatorHorn.wav` | `announce` | 400 Hz diaphragm buzzer, harsh, rattling, boosted where the ear is sharpest. An alarm. |
| `Assets/Audio/AnnunciatorRingback.wav` | `clear` | 240 Hz, six partials, no rattle, no presence boost, quieter. An advisory. |

So **a rack wants two horns**: one `AnnunciatorHorn` with `Flash Rate` =
`announce` at 2 blips/second, one with `clear` at 1. Adding the component pulls
the clip that matches its rate, so set the rate first (or Reset the component
after changing it). Both clips are generated, not recorded —
`misc/tools/make_alarm_horn_wav.py` builds both, and every part of either sound
is a number in that file.

## Flash groups

Flashing is the client's job — `flashing` on the wire is a flag, not a rate — and
racks flash **as a panel**, not as separate windows. `AnnunciatorFlashGroups`
holds one clock per group name; every rack in the group reads its lit/dark phase
from that clock, so two windows can't drift apart because neither is counting.

- A rack's group comes from its definition's **Flash Group**, or the **Flash
  Group Override** on the instance if you'd rather not touch the definition.
  Racks with no group given all share the default one.
- Put two racks in the same group and their windows blink together — that's the
  whole of "in sync across racks".
- The rate is the definition's **Flash Seconds** (half a cycle). The first rack
  to register a group sets it; a later one asking for a different rate is warned
  and the group keeps the rate it has, because a group with two rates isn't one.
- A group whose windows were all steady **resyncs when the first one starts
  flashing**, so a new alarm comes in lit rather than mid-cycle. It doesn't
  resync while anything else is already flashing — that would jog the ones that
  are.

Timing is unscaled, like the sync loop: a paused simulation doesn't freeze an
alarm mid-blink.

`AnnunciatorRack.SetLampTest(true)` lights every window steady and hands them
back to the server when it goes off (there are buttons for it on the rack's
Inspector in play mode). Building racks is in
`docs/interactable-api-usage-guide.md`.

## Server-driven lamps

Once the server sends a state for an indicator, **the server owns those lamps** and
the local switch stops driving them (a lamp can be lit for reasons the switch
position doesn't show). States are `red`, `green`, and anything else meaning dark;
`flashing` blinks the lit lamp. `Invert Colors` is not applied to server states —
the server names the lamp outright. `ClearServerState()` hands the lamps back to
the switch.

## Debugging

- `IoSync` is on the `ServerConnection` object at runtime — select it in the
  hierarchy while playing. **Verbose** logs every applied change; it also reports
  how many controls got bound by UID on each sync.
- Two **switches or indicators** sharing a UID is logged as a warning and the
  second is ignored — they're inputs, and two controls reporting one UID would
  fight over it (see the duplication warning in
  `interactable-api-usage-guide.md`). Gauges are outputs, so sharing is allowed
  and every needle on the UID is driven; the verbose line counts needles and
  UIDs separately.
- A uid the server has no definition for is warned about once, then ignored.
- Failed requests are retried at the normal interval; the log is throttled so a
  stopped server doesn't fill the console.
- From the Python side, `state.get_switch(uid)["updatedBy"]` tells you which
  client (or `"server"`) last moved a switch.

Server side, including how to read and write this state from Python:
`server-python/API.md`.
