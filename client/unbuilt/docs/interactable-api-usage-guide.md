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
 7. **Add a controller to the `model`.** Select the `model` and in Inspector > Add Component > Scripts > select a controller (list of all controllers can be found in Assets/Scripts/Switch Controllers, Ang2p solves most cases).
 8. **Add objects and definitions.** Still in Inspector with `model` selected, drag the `moving-part` onto the `Handle` field. Then, drag the definition you have previously created onto the `Definition` field.
 9. **Fine-tune the animation.** While in-game, select the `model` and in Inspector adjust the settings for your controller class.

## Switch controllers

API for different switch controllers

## Gauges (GaugeDefinition + baked dial faces)

Dial faces are **baked to a texture from data** — no decals. A `GaugeDefinition` describes the scale (range, ticks, color bands, sweep); the baker generates `<name>_Face.png` + an HDRP/Lit `<name>_Face.mat` next to the definition and links them into it. `GaugeNeedle` maps values through the same definition, so needle and markings always agree.

 1. **Create a definition.** R-Click in Assets/Controls/Definitions > Create > NPP > Gauge Definition. Generate a UID the same way as for switches (three dots > Generate New ID).
 2. **Describe the scale.** Min/max, units, major tick interval (numbered ticks), minor ticks per major, label format/multiplier (`x100` dials: multiplier 0.01 with the real range, or 100 with a small range — your pick). Sweep angles: 0° = 12 o'clock, clockwise positive; default -135..+135 (a standard 270° gauge). Add color bands (in scale values) for normal/caution/danger arcs.
 3. **Bake.** Click **Bake Dial Face** at the bottom of the Inspector — a preview appears below the button. Re-bake anytime; the PNG and material update in place, so every gauge already using them updates too.
 4. **Apply the face.** Put the baked material on a quad/disc parented under the gauge model, sitting ~1 mm in front of the face body (behind the needle and glass). This replaces the decal workflow entirely.
 5. **Add the needle driver.** Add `GaugeNeedle` to the gauge model root, drag the needle mesh onto `Needle` and the definition onto `Definition`. The needle's authored rotation is taken as 12 o'clock. If it sweeps the wrong way in play mode, negate `Rotation Axis`.
 6. **Verify the bake.** In play mode, enable `Use Test Value` and scrub `Test Value` — the needle must point at the matching printed numbers. Other scripts drive the gauge via `GaugeNeedle.SetValue(float)` (looked up by definition UID, same pattern as switches).

## Lamp indicators (SwitchLampIndicator)

Drives a Red/Green lamp pair from a switch's state. By default: switch **ON** → Red mesh gets `Lamp Red Lit`, Green mesh gets `Lamp Green`; switch **OFF** → Red gets `Lamp Red`, Green gets `Lamp Green Lit`.

 1. **Select the `switch lamps` object** (in the switch prefab or a scene instance) and Add Component > `Switch Lamp Indicator`.
 2. **Assign the lit materials.** Drag `Lamp Red Lit` onto `Red Lit` and `Lamp Green Lit` onto `Green Lit` (from Assets/Controls/Models/Materials). The unlit slots are optional — if left empty, the materials currently on the meshes are used as the unlit state.
 3. **Lamp meshes are found automatically** by child name (`Red` / `Green`). Only assign the `Red Mesh` / `Green Mesh` fields manually if your meshes are named differently.
 4. **Bind the switch.** Leave `Definition` empty to follow the switch the lamps are a child of (the normal case for the template). To mirror a *different* switch, drag that switch's definition (.asset) onto the `Definition` field — the lamp looks the switch up by its UID at runtime.
 5. **Invert Colors** (optional) swaps the mapping: ON → Green lit, OFF → Red lit.