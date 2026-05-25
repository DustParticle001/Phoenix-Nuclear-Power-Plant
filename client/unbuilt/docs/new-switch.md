# Adding new interactable switches

## Instructions on adding a new interactable switch

### **Warning: DO NOT duplicate switches in the Hierarchy unless you know what you're doing. Definitions will NOT duplicate which, unless swapped for a different definition, will result in weird behaviour.**

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
 9. **Fine-tune the animation.** While in-game, select the `model` and in Inspector adjust (from now on assuming you use Ang2p controller, more docs on other controllers yet to come) `On Rotation` and `Off Rotation` to control the 2 positions of the switch. Use `Split Axis` to change the axis that is used to set the two sides that receive clicks to turn the switch and `Invert Sides` to swap them. Use `Speed` to adjust switching speed.