using System.Collections.Generic;
using UnityEngine;

// One SART cluster: silence, acknowledge, reset, test. Put this on the ROOT of
// the panel prefab and type in the SART group it commands. That is all of it.
//
// The four buttons are found by GameObject name and named from the group, so
// they need no definition assets of their own:
//
//     Sart Group "RCP P1"  ->  "RCP P1 Silence", "RCP P1 Acknowledge",
//                              "RCP P1 Reset",   "RCP P1 Test"
//
// Those are the names the server reads to work out which cluster it is and
// which windows it commands (server/annunciator_sim.py), so ONE field is the
// whole of the wiring. Stamp the prefab out per panel and set the group on each
// copy; the buttons inside come along already named.
//
// SART GROUP IS NOT THE FLASH GROUP. A flash group is every rack that blinks in
// step - a whole control room, usually - while a SART panel commands the one to
// three racks standing in front of it. So the two are separate names on the rack
// definition, and this one has to match the racks' Sart Group, not their Flash
// Group.
//
// Leave Sart Group empty and the cluster is the MASTER - it commands every
// window in the plant, whatever group they are in. That is the right answer
// while there is one panel, and it is what a plant-wide cluster is later.
//
// The buttons stay ordinary switches. Each syncs on its own exactly as it would
// with a definition of its own, which is what lets one operator watch another
// press them, and what makes the position arbitration in Trans2pSpring apply.
// A button that DOES have a definition assigned keeps it: this is the fallback,
// not an override.
[DisallowMultipleComponent]
public class SartPanel : MonoBehaviour, IControlIdSource
{
    // The four actions. A button's GameObject name has to read as one of these,
    // and the id it gets is the group and the canonical name - which is what
    // annunciator_sim.py classifies. Aliases are here rather than on the server
    // because the server sees only the id this produces.
    private static readonly (string Action, string[] Names)[] Buttons =
    {
        ("Silence",     new[] { "silence" }),
        ("Acknowledge", new[] { "acknowledge", "ack" }),
        ("Reset",       new[] { "reset" }),
        ("Test",        new[] { "test", "lamp test" }),
    };

    // What a nameless panel calls its buttons. "Annunciator" reads as a word
    // that describes a panel rather than naming one, which is exactly how the
    // server takes it: prefix ignored, every window commanded.
    private const string MasterPrefix = "Annunciator";

    [Header("Panel")]
    [Tooltip("SART group this cluster commands - the Sart Group on the rack definitions it works, " +
             "NOT their Flash Group (a control room flashes in step; a SART panel commands the one " +
             "to three racks in front of it). Empty = every window in the plant (a master cluster).")]
    [SerializeField] private string _sartGroup = "";

    // The group this panel commands, or "" for all of them.
    public string SartGroup =>
        string.IsNullOrWhiteSpace(_sartGroup) ? "" : _sartGroup.Trim();

    // What the buttons under this panel are called on the wire.
    public string Prefix => SartGroup.Length > 0 ? SartGroup : MasterPrefix;

    // --- IControlIdSource ---------------------------------------------------

    public string IdFor(MonoBehaviour control)
    {
        if (control == null)
            return null;

        string action = ActionOf(control.name);

        // Something else parented under the panel - a lamp, a label, a switch
        // that isn't one of the four. Not ours to name.
        return action != null ? Prefix + " " + action : null;
    }

    // --- checks -------------------------------------------------------------

    // A panel that is missing a button, or has two of one, is a panel that
    // quietly doesn't work: the server would simply never see that action. Say
    // so once, at startup, rather than leaving it to be noticed in the room.
    private void Start()
    {
        var seen = new Dictionary<string, string>();

        foreach (ISwitchControl control in GetComponentsInChildren<ISwitchControl>(true))
        {
            if (!(control is MonoBehaviour behaviour))
                continue;

            string action = ActionOf(behaviour.name);
            if (action == null)
                continue;

            if (seen.TryGetValue(action, out string first))
            {
                Debug.LogWarning(
                    $"[SartPanel] '{name}' has two {action} buttons ('{first}' and " +
                    $"'{behaviour.name}'). They report one uid, so IoSync keeps the first " +
                    "and the other does nothing.", this);
                continue;
            }

            seen[action] = behaviour.name;

            if (control.Definition != null)
                Debug.Log($"[SartPanel] '{name}' leaves {action} to its own definition " +
                          $"({control.Definition.name}) rather than naming it.", this);
        }

        foreach ((string action, string[] names) in Buttons)
        {
            if (seen.ContainsKey(action))
                continue;

            Debug.LogWarning(
                $"[SartPanel] '{name}' has no {action} button. Name a child object " +
                $"'{names[0]}' (any capitalisation) and it will be picked up as " +
                $"'{Prefix} {action}'.", this);
        }
    }

    // --- naming -------------------------------------------------------------

    // The canonical action a GameObject name reads as, or null. Exact match on
    // the whole name so a "Test Lamps" label or a "Reset Permissive" switch
    // sitting in the panel isn't mistaken for a button.
    private static string ActionOf(string objectName)
    {
        if (string.IsNullOrWhiteSpace(objectName))
            return null;

        string trimmed = objectName.Trim();

        foreach ((string action, string[] names) in Buttons)
        {
            foreach (string alias in names)
            {
                if (trimmed.Equals(alias, System.StringComparison.OrdinalIgnoreCase))
                    return action;
            }
        }

        return null;
    }
}
