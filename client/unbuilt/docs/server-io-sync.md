# Live I/O sync (switches, indicators, gauges)

`IoSync` keeps the scene and the server in step on a timer. One request per tick
does both directions:

| Direction | What moves |
| --- | --- |
| up | the position of **every** switch definition in the loaded scene |
| down | switches other players moved, indicator lamp states, gauge values |

Everything is matched by **definition UID** — `SwitchDefinition.Id` for switches
and indicators, `GaugeDefinition.Id` for gauges. Nothing depends on object names
or hierarchy, and a control with no definition assigned is skipped (it has no UID
the server could key on).

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
   indicators through `SwitchLampIndicator.SetServerState`.

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

- **Switches** — any handler implementing `ISwitchControl` (`Rot2p`, `Rot3p`).
  Positions are the names on the wire: `off`/`on` for `Rot2p`,
  `left`/`center`/`right` for `Rot3p`.
- **Gauges** — any `GaugeNeedle`. Note that `Use Test Value` on the needle
  overrides server values; turn it off for gauges the server drives.
- **Indicators** — any `SwitchLampIndicator`. It answers to its own `Definition`
  if one is set, otherwise the UID of the switch it hangs under.

With `autoRegisterFromClients` on (the default), switches the server doesn't know
about are added to `data/io_definitions.json` on the first report, using the
definition's asset name and display name — so the file fills itself from the
scene instead of being typed out by hand. Watch the server console for
`[io] registered switch ...` lines.

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
- Two controls sharing a UID is logged as a warning and the second is ignored
  (see the duplication warning in `interactable-api-usage-guide.md`).
- A uid the server has no definition for is warned about once, then ignored.
- Failed requests are retried at the normal interval; the log is throttled so a
  stopped server doesn't fill the console.
- From the Python side, `state.get_switch(uid)["updatedBy"]` tells you which
  client (or `"server"`) last moved a switch.

Server side, including how to read and write this state from Python:
`server-python/API.md`.
