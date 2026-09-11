# Interactable API usage guide(s)

## Adding an interactable

Instructions on adding a new interactable

### **Warning: DO NOT duplicate interactables in the Hierarchy unless you know what you're doing. Definitions will NOT duplicate which, unless swapped for a different definition, will result in weird behaviour.**

 1. **Add the model** somewhere to Assets (preferably Assets/Controls/Models) or **use an existing one.**
 2. **Load the model into the scene.** Ensure you have the following structure:
```
    model
    ├── fixed-part
    └── moving-part
    
    // the actual model and mesh names would differ
```
 3. **Create a new definition (.asset).** In unity, go to Assets/Controls/Definitions (or a folder of your choice). R-Click > Create > Controls > Switch Definition. Name the definition according to your switch as it is unique to every switch and gives it a UID to later read the switch's state from other scripts.
 4. **Generate a UID.** Select your definition, then, in Inspector above the `Open` button click the three dots > Generate New ID. An ID should appear. Optionally, set a display name.
 5. **Set the layer to Interactable** on the `model`and `moving-part`. Select the `model` and in Inspector below and to the right of the object's name is a layer dropdown. Select Interactable in it. Repeat for the `moving-part`.
 6. **Add a BoxCollider to the `moving-part`.** Select the `moving-part` and in Inspector > Add Component > search for Box Collider. Adjust collider if needed.
 7. **Add a controller to the `model`.** Select the `model` and in Inspector > Add Component > Scripts > select a controller (they all live in Assets/Scripts/Switch Handlers and are listed under [Switch controllers](#switch-controllers) below; `Rot2p` solves most cases).
 8. **Add objects and definitions.** Still in Inspector with `model` selected, drag the `moving-part` onto the `Handle` field. Then, drag the definition you have previously created onto the `Definition` field. (On a pushbutton the `Handle` is the cap - every controller takes the same field, whatever its moving part happens to be called.)
 9. **Fine-tune the animation.** While in-game, select the `model` and in Inspector adjust the settings for your controller class.

## Switch controllers

API for different switch controllers

They all live in `Assets/Scripts/Switch Handlers`, go on the **model root**
(never on the moving part), and take the same two fields: the `Handle`, whatever
it is that moves, and the `Definition` that gives the control its UID. What
differs is how the handle moves and whether it stays where you put it.

| Controller | Motion | Positions (the wire format) | Behaviour |
| --- | --- | --- | --- |
| `Rot2p` | rotates | `off` / `on` | Latches. Click a side to throw it that way. Solves most cases. |
| `Rot3p` | rotates | `left` / `center` / `right` | Latches. A maintained **selector** — transfer scheme mode, meter selection. From either end, a click returns it to centre. |
| `RotNp` | rotates | `p1` … `pN` | Latches. `Rot3p` past three positions: a multiposition selector, one detent per click. Detents evenly stepped or angled one by one. |
| `Rot2pSpring` | rotates | `off` / `on` | Rests in `off` and is only `on` while you hold the mouse button. Lamp test, alarm reset, master reset. |
| `Rot3pSpring` | rotates | `left` / `center` / `right` | Rests in `center`; hold a side to sit there. The breaker control switch — TRIP / normal / CLOSE. Either end can be made maintained instead. |
| `Trans2p` | translates | `released` / `pressed` | Latching pushbutton: the cap sinks in and stays. A mode select, a defeat, an isolation. |
| `Trans2pSpring` | translates | `released` / `pressed` | Momentary pushbutton: in while held, out when you let go. Reactor trip, alarm acknowledge. |

Positions are **geometry, not meaning** — `left`/`center`/`right`, not
`trip`/`normal`/`close` — and a spring-return controller uses the same names as
its latching counterpart. So a definition can move from `Rot2p` to `Rot2pSpring`,
or from `Rot3p` to `Rot3pSpring`, without the server noticing: the switch is a
different piece of hardware, and the signal it drives isn't.

Buttons come in two positions only. A pushbutton has an in and an out; there is
no three-position button on a control panel.

### Multiposition selectors

`RotNp` is `Rot3p` carried past three positions — the meter selector that reads
six points off one gauge, a frequency selector, a synchroscope's incoming-line
switch. It latches, like `Rot3p`: a detent is a state, not a command. One click
is one detent, and which side of the handle you hit decides which way it turns
(`Split Axis` / `Invert Sides`, the same fields as every rotary here).

Both ways of placing the detents measure from the handle's **modelled**
rotation, read once on scene load, exactly as `Trans2p` measures travel from the
cap's modelled position — so the modeller poses the handle where it belongs and
there is no per-position `Vector3` to keep in step with the model afterwards.
`Turn Axis` is the shaft it turns about, in the handle's own space.

 - **Even Step** — the usual one. A rotary has evenly spaced detents, so
   `Position Count` and `Degrees Per Position` describe all of them (negate the
   step to turn the other way). `Rest Position` is the detent the handle was
   modelled in: leave it at 1 and the switch sweeps one way from the modelled
   pose; set it to the middle detent and it sweeps both ways.
 - **Per Position** — `Position Angles`, one angle from the modelled pose per
   detent, for the switches that aren't even: a wide gap where a detent was
   left out, or an OFF that sits away from the rest. **How many entries there
   are is how many positions the switch has** — `Position Count` is ignored in
   this mode.

`Default Position` is where it starts, counting from 1. `Wrap` is off by
default, so it stops at the end detents like a switch with end stops; turn it on
for the ones that go round.

Positions on the wire are `p1`…`pN` — geometry, not meaning, like everywhere
else. What detent 3 selects belongs in the server's I/O map; on this side it is
the third detent, and `/turnswitch <switch> 3` moves it there because the
console already takes a 1-based number as well as a name.

**Settle the detent count before the server first sees the switch.** The server
takes a switch's position list once, when it auto-registers the uid, and only
the position comes up after that — so growing a 4-position switch to 6 leaves
the server knowing four, and reports of `p5` are dropped as a position it has
never heard of. Either fix the count first, or delete that switch from
`server/data/io_definitions.json` and let it register again.

From a script it counts detents the way the panel is engraved: `CurrentPosition`
and `SetPosition(int)` are 1-based, `PositionCount` is however many there are,
`Step(int)` turns it by detents, and `OnPositionChanged` carries the new number.

There is no spring-return variant, because a multiposition selector is a
maintained control. A three-position switch whose ends are momentary is
`Rot3pSpring`. `SwitchLampIndicator` doesn't follow a `RotNp` either — it
mirrors a `Rot2p`'s on/off and nothing else, so a lamp on one of these is driven
by the server outright.

### Spring-return controllers

`Rot2pSpring`, `Rot3pSpring` and `Trans2pSpring` are only off their rest
position while the mouse button is **held down** — click and release and they
throw and come straight back, which is the whole point of them: the position is
a command, not a state. The hold is tracked from the press, so you can look away
mid-hold and the switch stays thrown. In the room your hand doesn't move because
your eyes did.

None of them has a start-position field. A spring switch starts wherever its
spring leaves it.

 - **Minimum Hold Seconds** (0.25 s) is the shortest time the control stays off
   its rest position, however briefly it was clicked. `IoSync` reports positions
   on a **timer**, so a press shorter than one tick would otherwise fall
   entirely between two reports and never reach the server at all — and on a
   momentary control that press is the entire signal. Keep it at or above the
   server's report interval (0.2 s by default). The cost is that two taps inside
   that window read as one press, which at 0.2 s is below what a position-based
   wire format can distinguish anyway.
 - **The operator's hand wins.** While the button is down, a position arriving
   from the server is ignored: the server can hold a stale rest position for a
   tick after the press was reported, and snapping back under a held mouse
   button is worse than being a tick behind. A position arriving while nothing
   is held is applied normally — that one is another player's hand on their own
   copy of the switch, and they are the one who will let go of it.
 - **`Rot3pSpring` ends can be maintained.** Turn `Left Spring Return` or
   `Right Spring Return` off and that end latches instead, for the switches that
   spring one way and stay put the other (a pump control switch whose START
   springs back but whose PULL-TO-LOCK doesn't). A latched end then behaves like
   `Rot3p`: a click brings it back to centre.

### Pushbuttons

`Trans2p` and `Trans2pSpring` translate the cap instead of rotating a handle —
otherwise same philosophy, same fields, same sync. The model structure is the
one every other control uses, with the cap as the `moving-part`.

The cap's **authored local position is the released one**, read once on scene
load, so the modeller places the button where it belongs and the controller only
ever pushes it in from there. Travel is given as a direction plus a depth rather
than as a second position, so it can be tuned with a single number in play mode:

 - **Press Axis** — local direction the cap travels, in the space it sits in
   (default `(0, 0, -1)`). Negate it if the button pops out instead of sinking
   in. It is normalized, so its length doesn't quietly scale the depth.
 - **Press Depth** — how far, in metres. 4 mm by default, which reads as a
   button rather than as a tile.
 - **Speed** — 25 by default. A button snaps; it doesn't swing like a handle.

A button has no sides, so where on it you click is nothing to it — anywhere on
the cap does the one thing the cap does.

### Making a new controller sync with the server

Implement `ISwitchControl` (Assets/Scripts/Switch Handlers/ISwitchControl.cs) and
`IoSync` picks the switch up automatically — no registration anywhere:

```csharp
public class MyController : MonoBehaviour, ISwitchControl
{
    public SwitchDefinition Definition => _definition;          // usually already there
    public string Id => _definition != null ? _definition.Id : "unassigned";
    public string[] Positions => _positionNames;                // e.g. { "off", "on" }
    public string Position => /* which one it's in now */;
    public void SetPosition(string position) { /* move it, or warn */ }
}
```

Position names are the wire format for that switch, so keep them lowercase and
stable — renaming one renames it in the server's I/O map too. See
`docs/server-io-sync.md`.

Clicks arrive the same way. Implement `IInteractable` (same folder) and
`InteractionManager` finds the controller through whatever collider the ray hit.
It knows no class names, so there is nothing to add to it:

```csharp
public void OnInteract(Vector3 worldHitPoint) { /* clicked */ }
```

If the control only holds its position while the mouse button is down, implement
`IHoldInteractable` instead — `OnInteract` plus an `OnRelease()`. The manager
remembers which control it pressed and releases that one, which is what lets a
player look away mid-hold.

Both interfaces go on the component on the **model root**, the same one that
carries `ISwitchControl`: `GetComponentInParent` walks up from the collider on
the moving part to find it.

## Gauges (GaugeDefinition + baked dial faces)

Dial faces are **baked to a texture from data** — no decals. A `GaugeDefinition` describes the scale (range, ticks, color bands, sweep); the baker generates `<name>_Face.png` + an HDRP/Lit `<name>_Face.mat` next to the definition and links them into it. `GaugeNeedle` maps values through the same definition, so needle and markings always agree.

 1. **Create a definition.** R-Click in Assets/Controls/Definitions > Create > NPP > Gauge Definition. Generate a UID the same way as for switches (three dots > Generate New ID).
 2. **Describe the scale.** Min/max, units, major tick interval (numbered ticks), minor ticks per major, label format/multiplier (`x100` dials: multiplier 0.01 with the real range, or 100 with a small range — your pick). Sweep angles: 0° = 12 o'clock, clockwise positive; default -135..+135 (a standard 270° gauge). Add color bands (in scale values) for normal/caution/danger arcs.
 3. **Bake.** Click **Bake Dial Face** at the bottom of the Inspector — a preview appears below the button. Re-bake anytime; the PNG and material update in place, so every gauge already using them updates too.
 4. **Apply the face.** Put the baked material on a quad/disc parented under the gauge model, sitting ~1 mm in front of the face body (behind the needle and glass). This replaces the decal workflow entirely.
 5. **Add the needle driver.** Add `GaugeNeedle` to the gauge model root, drag the needle mesh onto `Needle` and the definition onto `Definition`. The needle's authored rotation is taken as 12 o'clock. If it sweeps the wrong way in play mode, negate `Rotation Axis`.
 6. **Set the movement.** `Needle Response` on the definition is how long the pointer takes to catch a step change — the *instrument*, not the signal, so changing it needs no re-bake. The 0.02 s default is a rigid pointer that reads its input exactly, which is what a synchroscope needs. A switchboard ammeter has a pivot, a spring and damping and slams over in a fraction of a second rather than teleporting, so give it ~0.3; the RCP ammeters use that and their flow gauges 0.45.
 7. **Verify the bake.** In play mode, enable `Use Test Value` and scrub `Test Value` — the needle must point at the matching printed numbers. Other scripts drive the gauge via `GaugeNeedle.SetValue(float)` (looked up by definition UID, same pattern as switches).

## Lamp indicators (SwitchLampIndicator)

Drives a Red/Green lamp pair from a switch's state. By default: switch **ON** → Red mesh gets `Lamp Red Lit`, Green mesh gets `Lamp Green`; switch **OFF** → Red gets `Lamp Red`, Green gets `Lamp Green Lit`.

 1. **Select the `switch lamps` object** (in the switch prefab or a scene instance) and Add Component > `Switch Lamp Indicator`.
 2. **Assign the lit materials.** Drag `Lamp Red Lit` onto `Red Lit` and `Lamp Green Lit` onto `Green Lit` (from Assets/Controls/Models/Materials). The unlit slots are optional — if left empty, the materials currently on the meshes are used as the unlit state.
 3. **Lamp meshes are found automatically** by child name (`Red` / `Green`). Only assign the `Red Mesh` / `Green Mesh` fields manually if your meshes are named differently.
 4. **Bind the switch.** Leave `Definition` empty to follow the switch the lamps are a child of (the normal case for the template). To mirror a *different* switch, drag that switch's definition (.asset) onto the `Definition` field — the lamp looks the switch up by its UID at runtime.
 5. **Invert Colors** (optional) swaps the mapping: ON → Green lit, OFF → Red lit.

### A single lamp on its own

The same component also does a lamp that is nobody's pair — a pump run light
standing on the panel rather than a pair sitting on a switch. Leave `Green Mesh`
empty, leave `Definition` empty, and hang it under no switch: it then answers to
its **own object's name** and is driven entirely by the server. That is how the
`cube-indicator-white` template works, and why the run lights in the scene are
called `RCP 1 Run Lamp` and so on — the name is the uid the server drives them
by, so renaming the object renames it there too. Give it a definition if you
want a name that survives being renamed.

A lamp like that logs nothing at startup, because having no switch is the point.
One that names a switch it cannot find still warns.

## Annunciator racks (AnnunciatorRackDefinition + generated model)

A rack is **described, not modelled**. One definition asset holds the size, the
grid, the legends and the lens colours; the builder generates the frame mesh with
a socket cut for every window, the lens mesh, the HDRP materials, the legends and
a prefab. Change anything and rebuild — the model, the materials and every
instance of the prefab follow.

 1. **Create a definition.** R-Click in Assets/Controls/Annunciators (or wherever
    you keep them) > Create > NPP > Annunciator Rack Definition. Generate a UID
    the same way as for switches (three dots > Generate New ID).
 2. **Size it.** `Width`/`Height` are the rack face in metres, `Cells X`/`Cells Y`
    how many windows across and down. Everything else follows from those:
    window size is what's left after the `Bezel Margin` around the outside and
    the `Rib Width` between windows. `Depth` is how far the box goes back,
    `Lens Recess` how deep each window's socket is.
 3. **Write the two CSVs.** One of legends, one of lens colours, in either shape:
    a **grid** laid out like the rack (one line per row, one field per window),
    or a **list** with a `row,column,text` header, counting from 1. A list with
    both a `text` and a `colour` column can be given to both importers. In a
    legend, `\n` or `|` starts a new line, and a lone `-` blanks that cell off:
    frame, no window. There are working examples of both in
    `Assets/Controls/Annunciators/Examples`.
 4. **Import.** Drop the CSVs into the `Labels Csv` / `Colors Csv` slots and press
    **Import Both** (or **Browse...** to read one from anywhere on disk). With
    `Resize To Csv` on, the labels file sets `Cells X`/`Cells Y` — the file is
    the rack. The Inspector then draws the rack as a grid of coloured windows,
    which is how you check the import landed where you meant it to.
 5. **Build.** Press **Build Model + Prefab**. Meshes go in `meshes/`, materials
    in `materials/`, and the prefab sits next to the definition. **Add To Scene**
    drops one in. Existing assets are rewritten rather than replaced, so scenes
    already using them keep working.
 6. **Group it.** `Flash Group` is what makes windows blink together — every rack
    carrying the same name flashes as one panel, and `Flash Seconds` (half a
    cycle) is the rate the first rack in a group sets. Leave it empty and the
    rack joins the default group. A rack in the scene can be pushed into another
    group with `Flash Group Override` without touching the definition.
 7. **Check it.** In play mode the rack's Inspector has **Lamp Test** (every
    window lit and steady), **Flash All** and **Clear All**. Lamps off hands the
    windows back to the server.

### Colours

Nine lens colours: `white`, `amber`, `red`, `green`, `blue`, and the x variants
`xamber`, `xred`, `xgreen`, `xblue`. A plain colour is **grey and colourless
until it lights**; an x colour keeps a dark version of itself while unlit
(`xgreen` for a running diesel, `xred` for a fire alarm — you can see the window
is there before it comes in). Both light the same. `dark red` and `x-red` are
read as `xred`, so a spreadsheet can spell it either way.

### SART (silence, acknowledge, reset, test)

The four pushbuttons that work a panel. There is a `SART Panel` prefab in
`Assets/Controls/Templates` built out of four `push-button` instances.

**One component, one field, no definitions.** Put `SartPanel` on the ROOT of the
panel and type in the SART group it commands:

 1. **Set `Sart Group`** on each rack definition (Inspector > Identity) to the
    panel that works it: `RCP P1`, `Turbine`, whatever. This is **not** the flash
    group — see below.
 2. **Add `SartPanel` to the panel root** (Add Component > Scripts > Sart Panel)
    and set its `Sart Group` to the same name. Spelling is loose: `RCP P1`,
    `RCP_P1` and `rcp-p1` are one name. **Leave it empty** and the cluster is
    the **master**: it commands every window in the plant, whatever group they
    are in, which is what a plant-wide cluster is.
 3. **That's it.** The four buttons are found by GameObject name — `Silence`,
    `Acknowledge` (or `Ack`), `Reset`, `Test`, any capitalisation — and named
    from the group: `RCP P1 Silence`, `RCP P1 Acknowledge`, and so on. Those
    names are what the server reads to work out which cluster it is and which
    windows it commands, so the group is the whole of the wiring. Stamp the
    prefab out per panel and set the group on each copy.

#### Sart Group is not Flash Group

They are two different partitions of the same racks, and a rack definition
carries both:

| | Groups | Scope |
| --- | --- | --- |
| **Flash Group** | racks that blink and sound **in step** | usually a whole control room |
| **Sart Group** | racks **one SART panel commands** | the one to three racks in front of it |

A control room flashes as one panel because that is what an operator sees from
across it; a SART cluster works the racks within reach. Using one name for both
would tie the panel you can reach to the panel you can see, so a rack in the
`MCR` flash group can be in the `RCP P1` SART group, and its neighbour in
`Turbine`.

A rack whose `Sart Group` is empty is reached **only by a master cluster** —
guessing which of several panels commands it would be worse than doing nothing.
A cluster whose name matches no rack's `Sart Group` commands everything instead,
and says so once in the server console, so a half-configured panel still works
while you finish wiring it up.

Both have an override on the rack **instance** (`Flash Group Override`,
`Sart Group Override`) for reassigning one rack without touching the definition
every copy of it shares.

Change either on the definition and the racks follow: the client notices the
server's copy has gone stale and re-reports the windows, and a window that was
in alarm stays in alarm through the move.

`SartPanel` says so at startup if a button is missing or doubled, because a
panel with no Reset is a panel that quietly doesn't reset.

The buttons want `Trans2pSpring` (momentary). A latching switch works but has to
be flipped back to arm the next press, and would hold the panel in test forever.

**Why no definitions.** A `SwitchDefinition` is one asset holding one UID, which
is right for a control that exists once — there is one Gen Breaker switch. A
cluster you place several copies of is the opposite case: the definition would
live in the prefab and every copy would answer to the same UID, so each panel
would need four new assets bound by hand. Instead a control with no definition
asks upwards for a name (`IControlIdSource`), and the panel answers. Every
controller does this, so the same trick works for any cluster built as one
prefab. A button that *does* have a definition keeps it — this is the fallback,
not an override.

What each one does, and what the panel looks like while it does it:

| | Lamp | Horn |
| --- | --- | --- |
| alarm in, unacknowledged | fast flash | alarm horn |
| **SILENCE** | unchanged, still flashing | silent |
| **ACKNOWLEDGE** | steady lit | silent |
| condition goes away | slow flash (ringback) | ringback |
| **RESET** | out | silent |

A window reaches ringback whether or not anyone acknowledged the alarm, and only
RESET takes it dark from there. ACKNOWLEDGE is for the alarm; RESET is the
ringback's acknowledge. **TEST** held makes every window on the panel read as
being in alarm, so letting go drops the whole panel into ringback — the entire
sequence from one button.

Silence is per window, not per panel: it quiets what is in **now** and the next
alarm still sounds. See `docs/server-io-sync.md` for the wire format and
`server/annunciator_sim.py` for the sequence itself.

### Horns

**A rack wants two of them**, because the two flash rates have separate sounds
and the ear has to tell them apart from across the room without reading a
legend:

| `Flash Rate` | `Blips Per Second` | Clip | What it is |
| --- | --- | --- | --- |
| `announce` | 2 | `Assets/Audio/AnnunciatorHorn.wav` | 400 Hz diaphragm buzzer, harsh and rattling. An alarm. |
| `clear` | 1 | `Assets/Audio/AnnunciatorRingback.wav` | 240 Hz, smooth, no rattle, quieter. An advisory. |

**They cannot share a GameObject.** A horn owns its `AudioSource` — that is how
the sound comes from that rack's place on the wall — and two of them on one
source would fight over its volume every frame, so `AnnunciatorHorn` is
`[DisallowMultipleComponent]` and Unity refuses the second one. Two horns are
two objects, which is also what two horns physically are.

So: **right-click the horn you have > "Add The Other Horn"**. It makes a child
object on the other rate, at that rate's blip interval, with that rate's clip
and the `AudioSource` set up, and tells you if the other horn already exists. A
child still finds the rack through its parents, so it joins the same group.

The blips are timed by the group's shared clock rather than by each horn, so
every rack in a group sounds on the same frame however many racks there are.

Both clips are generated rather than recorded: `misc/tools/make_alarm_horn_wav.py`
builds both, and every part of either sound is a number in that file.

### What the server sees

Each window gets a uid when it's imported and keeps it across rebuilds, so a rack
holds its identity on the server however often you rebuild it. The client
registers its windows with the server on the first sync and the server drives
them from there (`state` + `flashing`); the lens colour stays the client's.
Simulations address windows by the **readable id** — the legend slugged,
`RCP 1 / TRIP` → `RCP_1_TRIP` — because the uid is a GUID nobody wants to
type. Give the CSV an `id` column to name them yourself. See
`docs/server-io-sync.md` and `server/API.md`.
