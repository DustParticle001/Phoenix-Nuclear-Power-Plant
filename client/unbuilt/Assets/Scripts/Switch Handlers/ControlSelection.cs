// ControlSelection.cs
using UnityEngine;

// For a device that carries several controllers on ONE GameObject - a station
// of four pushbuttons modelled as one object, a pair of switches on one
// escutcheon. Each controller still has its own handle; the handle is what
// tells them apart.
//
// Everything that used to ask "which controller is above me?" with
// GetComponentInParent got the first one on the object and nothing else. That
// is still the answer when there is only one, and everything here collapses to
// exactly the old behaviour in that case. With several:
//
//   - Something under a handle belongs to that handle's controller: the collider
//     on a button cap, the lamp inside an illuminated pushbutton.
//   - Otherwise it belongs to the controller whose handle is nearest - a lamp
//     sitting beside its switch, a click on the body next to a button.
//   - A controller is named after its handle rather than the object, since the
//     object's name is shared by all of them (see NameOf).
public static class ControlSelection
{
    // The controller of type T that `from` belongs to: the nearest object at or
    // above `from` that carries any T, and among those, the one whose handle
    // `from` is under, or failing that the one whose handle is closest to
    // `near`. Null if nothing above carries a T.
    //
    // Walks the parents by hand rather than GetComponentInParent, because that
    // returns one component and this needs all of them on the same object.
    // Components on inactive objects are included, like
    // GetComponentInParent(true): IoSync's scan sees them, and a lamp it can see
    // has to resolve the same way.
    public static T Pick<T>(Transform from, Vector3 near) where T : class
    {
        for (Transform t = from; t != null; t = t.parent)
        {
            T[] found = t.GetComponents<T>();

            if (found.Length == 0)
                continue;
            if (found.Length == 1)
                return found[0];

            return Choose(found, from, near);
        }

        return null;
    }

    private static T Choose<T>(T[] candidates, Transform from, Vector3 near) where T : class
    {
        // Under a handle: that one, and the innermost if handles nest.
        T owner = null;
        Transform ownerHandle = null;

        foreach (T candidate in candidates)
        {
            Transform handle = HandleOf(candidate);
            if (handle == null || !from.IsChildOf(handle))
                continue;

            if (ownerHandle == null || handle.IsChildOf(ownerHandle))
            {
                owner = candidate;
                ownerHandle = handle;
            }
        }

        if (owner != null)
            return owner;

        // Nearest handle. A controller with no handle can't win this, and if
        // none has one we are guessing either way - take the first, as
        // GetComponentInParent would have.
        T nearest = candidates[0];
        float best = float.MaxValue;

        foreach (T candidate in candidates)
        {
            Transform handle = HandleOf(candidate);
            if (handle == null)
                continue;

            float distance = (handle.position - near).sqrMagnitude;
            if (distance < best)
            {
                best = distance;
                nearest = candidate;
            }
        }

        return nearest;
    }

    // True when the controller's object carries other controllers besides it.
    public static bool IsShared(MonoBehaviour control) =>
        control != null && control.GetComponents<ISwitchControl>().Length > 1;

    // What to call a controller when a name has to identify it - SartPanel
    // builds uids out of this. The object's name while it is the only
    // controller there (so nothing already built changes), the handle's name
    // once the object is shared, because then the object's name is everybody's.
    public static string NameOf(MonoBehaviour control)
    {
        if (control == null)
            return null;

        Transform handle = HandleOf(control);
        return handle != null && IsShared(control) ? handle.name : control.name;
    }

    // A click point in the controller's body frame, for working out which side
    // of it was clicked. The body frame rather than the handle's, because the
    // handle rotates and would tilt the split plane with it.
    //
    // Measured from the body's origin while the controller has the object to
    // itself - as it always was, so no tuned switch changes side. On a shared
    // object the origin is everybody's and would split most of the switches off
    // centre, so it is measured from this controller's handle pivot instead,
    // still along the body's axes.
    public static Vector3 LocalHit(MonoBehaviour control, Transform handle, Vector3 worldHitPoint)
    {
        Transform body = control.transform;
        Vector3 local = body.InverseTransformPoint(worldHitPoint);

        if (handle != null && IsShared(control))
            local -= body.InverseTransformPoint(handle.position);

        return local;
    }

    private static Transform HandleOf(object candidate)
    {
        // Interface references don't get Unity's destroyed-object ==, so check
        // through the component.
        if (candidate is Object unityObject && unityObject == null)
            return null;

        return (candidate as ISwitchControl)?.Handle;
    }
}
