# Plant System JSON Schema (v1)

Custom format for capturing US EPR plant systems as simulation graphs.
One file per system/unit under `references/systems/<system>/<unit>.json`.
Covers the **entire** system — MCR-visible controls *and* hidden devices
(relays, breakers, valve drives, auto logic) that the simulation needs.

Design phase order: SICS (hardwired) first; PICS soft-controls deferred.

## Top level

```jsonc
{
  "schemaVersion": 1,
  "system": "RCS",                 // system group abbreviation (see reference doc)
  "unit": "RCP",                   // device/unit this file describes
  "name": "Reactor Coolant Pump",
  "instances": ["RCP1", "RCP2"],   // identical copies; "{n}" in ids expands per instance
  "notes": "free text / FSAR sourcing caveats",

  "devices":      [ ... ],         // physical equipment (see Device)
  "signals":      [ ... ],         // measurements & derived/logic signals (see Signal)
  "logic":        { ... },         // permissives, auto-trips, sequences (see Logic)
  "mcr":          { ... },         // MCR-facing controls & indications (see MCR)
  "dependencies": [ ... ]          // interfaces to other system files (see Dependency)
}
```

## Device

```jsonc
{
  "id": "RCP{n}-BKR",              // unique; {n} = instance number
  "name": "RCP {n} supply breaker",
  "kind": "breaker",               // breaker | motor | pump | valve | relay | seal |
                                   // heat-exchanger | tank | sensor | transformer | bus | other
  "location": "switchgear",        // physical home: containment | switchgear | safeguard-bldg |
                                   // aux-bldg | turbine-hall | mcr-sics | ...
  "visibility": "hidden",          // "hidden" (sim-only) | "mcr" (has a control/indication)
  "states": ["open", "closed", "tripped"],
  "initialState": "open",
  "actuation": ["auto", "mcr", "local"],  // who can drive it
  "behavior": "free text: physics/response the sim must reproduce",
  "params": { }                    // numeric data (ratings, flows, timings); "~" = approximate
}
```

## Signal

```jsonc
{
  "id": "RCP{n}-SPEED",
  "name": "RCP {n} shaft speed",
  "type": "analog",                // analog | binary | derived
  "unit": "rpm",
  "source": "RCP{n}-MOTOR",        // device id, or "logic" for derived signals
  "range": [0, 1500],
  "expr": null                     // for derived: boolean/math expression over other ids
}
```

## Logic

Interlocks and automatic actions, written as readable boolean expressions
over device states and signal ids. These become sim code later.

```jsonc
{
  "permissives": [
    { "id": "RCP{n}-START-PERM", "allows": "close RCP{n}-BKR",
      "expr": "RCP{n}-OLP == running AND SEALINJ-FLOW-OK ...", "notes": "" }
  ],
  "autoActions": [
    { "id": "RCP-TRIP-ON-SI", "action": "trip RCP{n}-BKR (all)",
      "expr": "ESFAS-SI-ACTUATED", "notes": "" }
  ],
  "sequences": [                   // timed/staged automatic sequences
    { "id": "...", "trigger": "...", "steps": ["..."] }
  ]
}
```

## MCR

What appears on the panel. `control.kind` maps to Unity switch controllers
(existing: `rot2p`, `rot3p`; future: `pushbutton`, `pb-guarded`, `keyswitch`,
`indicator-lamp`, `gauge`, `digital-readout`, `annunciator`).
`defName` is the future SwitchDefinition asset name.

```jsonc
{
  "sics": [
    {
      "defName": "RCP1-TRIP-PB",
      "label": "RCP 1 TRIP",
      "control": { "kind": "pushbutton", "states": ["released", "pressed"] },
      "drives": "trip RCP1-BKR",          // for controls
      "reads": null,                       // for indications: signal/device id
      "layout": { "panel": "RCS", "row": 1, "col": 1 }   // logical grid; 3D placement later
    }
  ],
  "pics": []                       // deferred; keep empty for now
}
```

## Links

Explicit edges between devices — this is the diagram. Every connection the
visual diagram shows must exist here and vice versa.

```jsonc
{
  "from": "NBUS-{bus}",            // device id; prefixes: "external:<SYS>" = other system,
  "to": "RCP{n}-BKR",              // "logic:<id>" = logic block, "mcr:<defName>" = panel item
  "type": "power",                 // power | mech | fluid | cooling | control | signal
  "medium": "water",               // for fluid: water | oil | N2 | steam | air
  "bidirectional": false,          // default false (arrow from->to)
  "notes": ""
}
```

## Dependency

Interfaces this unit needs from other systems (each gets its own file eventually).

```jsonc
{ "system": "CVCS", "interface": "seal injection supply",
  "signals": ["SEALINJ-FLOW-RCP{n}"], "notes": "" }
```

## Conventions

- IDs: UPPERCASE, dash-separated, `{n}` for per-instance expansion.
- Device naming: **functional abbreviation in the ID** (`BKR`, `MOTOR`, `OLP`),
  **ANSI device number in the name/diagram label**, written instance-first
  (`RCP1-52`, not `52-RCP1`). Exceptions where the ANSI number IS the ID suffix:
  relays whose number is their common name (86 lockout, 87 differential, 27 UV
  -> `RCP1-86`), and breakers, which use 52-based IDs throughout this project
  (named after what they feed: `RCP1-BUS-52` master feeds the group bus,
  `RCP1-FDR-52` feeds the motor feeder, `RCP1-MCC-52` feeds the aux MCC).
- Transformers follow the same feeds-rule with `-XFMR`: `RCP1-MCC-XFMR`,
  `SBO-BUS-1-XFMR`. Transfer switches likewise: `RCP1-MCC-ATS`, `SBO-BUS-1-ATS`
  (an ATS is NOT a breaker - no `-52`).
- Bus vs feeder: a **bus** is a node with multiple taps and gets a name
  (`NBUS-1`, `RCP1-BUS`, `RCP1-MCC`); a dedicated one-breaker-one-load line is
  a **feeder**, labeled `<load>-FDR` on the link, not a device.
- Selectivity: faults clear at the NEAREST upstream breaker; masters trip only
  via delayed backup relays (`-BUS-51` -> `-BUS-86`), never directly from a
  branch fault.
- Fluid/mechanical naming (mirrors the electrical feeds-rule): loop pipe legs
  are `RCS{n}-HL` / `RCS{n}-XL` / `RCS{n}-CL` (hot / crossover / cold leg);
  temperature elements `-TH-RTD` / `-TC-RTD`; flow elements `-FE`; SG primary
  plena `SG{n}-PRI-IN` / `SG{n}-PRI-OUT`; tube bundles `SG{n}-TUBES`.
  Taps and nozzles (SI, charging, letdown, spray, surge) are **links with
  notes**, not devices - a nozzle only becomes a device when it gets a valve
  or its own failure state.
- Numeric values that are estimates (no built US EPR exists) carry `"~"` prefix
  in strings or an `"approx": true` flag in params.
- `_manifest.json` tracks per-system status: `planned | diagrammed | serialized`.
