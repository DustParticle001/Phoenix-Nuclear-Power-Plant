// ISwitchControl.cs

// What IoSync needs from a switch handler to sync it with the server, so the
// sync code doesn't have to know whether it's driving a Rot2p, a Rot3p, or
// whatever comes next.
//
// Positions are the names the server stores and sends. Keep them lowercase and
// stable - renaming one changes the wire format for that switch.
public interface ISwitchControl
{
    // The SwitchDefinition UID this control is bound to ("unassigned" if none).
    string Id { get; }

    // The definition itself, for its asset name and display name. May be null.
    SwitchDefinition Definition { get; }

    // Every position this switch can be in, in order.
    string[] Positions { get; }

    // The position it is in now; always one of Positions.
    string Position { get; }

    // Move it, as the server says. Unknown names are ignored with a warning.
    void SetPosition(string position);
}
