// IControlIdSource.cs
using UnityEngine;

// A component that names the controls beneath it, for a panel built as ONE
// prefab you stamp out.
//
// Normally a control gets its identity from a SwitchDefinition asset: one asset
// per control, with a UID generated into it. That is right for a control that
// exists once - there is one Gen Breaker switch and it has one definition. It
// is wrong for a cluster you place several copies of, because the definition
// lives in the prefab and every copy would answer to the same UID; the four
// buttons of a SART panel would need four new assets, bound by hand, per panel.
//
// So a panel can name them instead. A control with no definition assigned asks
// upwards for an id, and whatever answers is responsible for it being stable
// (it is a UID: the server keys everything it holds by it) and unique across
// the scene. SartPanel builds one out of the group it commands and the button's
// own name - "RCP P1 Acknowledge" - so typing the group into one field is the
// whole of the wiring.
//
// A definition, where there is one, always wins: this is the fallback, not an
// override.
public interface IControlIdSource
{
    // A UID for this control, or null/empty to leave it unassigned (which means
    // IoSync skips it, exactly as an unbound control is skipped today).
    string IdFor(MonoBehaviour control);
}

// How every controller resolves the UID it reports. One place, because the
// answer has to be the same for all of them: the definition if there is one,
// otherwise whatever panel above it will name it, otherwise nothing.
public static class ControlId
{
    public const string Unassigned = "unassigned";

    public static string Resolve(MonoBehaviour control, SwitchDefinition definition)
    {
        if (definition != null)
            return definition.Id;

        if (control == null)
            return Unassigned;

        // Interfaces are fine here: GetComponentInParent walks up from this
        // control, so a panel anywhere above it answers. Inactive included,
        // because IoSync's scan includes inactive controls - a control it can
        // see has to be able to find the panel that names it, or it would
        // register as unassigned and silently never sync.
        IControlIdSource source = control.GetComponentInParent<IControlIdSource>(true);
        string id = source != null ? source.IdFor(control) : null;

        return string.IsNullOrWhiteSpace(id) ? Unassigned : id.Trim();
    }
}
