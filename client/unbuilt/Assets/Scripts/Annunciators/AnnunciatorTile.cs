// AnnunciatorTile.cs
using UnityEngine;

// One window on an annunciator rack: the lens, the legend printed on it, and
// the uid the server drives it by.
//
// The whole of a window's behaviour is two bits - lit or dark, flashing or
// steady - so this swaps between two materials the builder generated for its
// colour and leaves the blinking to its group (AnnunciatorFlashGroups), which
// is what keeps every flashing window on the panel in step.
//
// IoSync finds these by uid the way it finds gauges and switches, so nothing
// needs wiring: build a rack, drop it in the scene, and its windows are live.
// Serialized fields are filled in by Editor/AnnunciatorRackBuilder.cs.
[DisallowMultipleComponent]
public class AnnunciatorTile : MonoBehaviour
{
    [Header("Identity")]
    [Tooltip("Definition UID from the rack definition - what the server keys this window by.")]
    [SerializeField] private string _uid;
    [Tooltip("Readable id a simulation names it by, e.g. RCP_1_TRIP.")]
    [SerializeField] private string _id;
    [SerializeField] private string _legend;
    [SerializeField] private AnnunciatorRackDefinition.TileColor _color;
    [Tooltip("Used only if this window isn't under an AnnunciatorRack.")]
    [SerializeField] private string _flashGroup = "";

    [Header("Parts")]
    [SerializeField] private MeshRenderer _lens;
    [SerializeField] private Material _litMaterial;
    [SerializeField] private Material _unlitMaterial;

    // What IoSync keys on. "unassigned" means the builder never got to it.
    public string Id => string.IsNullOrEmpty(_uid) ? "unassigned" : _uid;
    public string ReadableId => _id;
    public string Legend => _legend;
    public AnnunciatorRackDefinition.TileColor LensColor => _color;
    public string ColorName => AnnunciatorRackDefinition.WireName(_color);

    // Free-form, as the server sent it; Lit is what it came out as.
    public string State { get; private set; } = "clear";
    public bool Lit { get; private set; }
    public bool Flashing { get; private set; }

    // Which clock this window blinks on while it flashes: "announce" for an
    // unacknowledged alarm, "clear" for ringback. Sent by the server.
    public string FlashRate { get; private set; } = AnnunciatorFlashGroups.AnnounceRate;

    // SILENCE was pressed on this window: it goes on flashing exactly as it
    // was and stops feeding the horn. Set by the server, which owns the
    // sequence - one operator's silence is heard by everyone in the room.
    public bool Silenced { get; private set; }

    public bool InLampTest { get; private set; }

    // States that read as dark. Everything else - "alarm", "cleared-unacked",
    // whatever a future system invents - lights the window, so a server can
    // name states freely without the client having to keep up.
    private static readonly string[] DarkStates =
        { "clear", "off", "normal", "reset", "none", "false", "0" };

    private AnnunciatorRack _rack;

    // The group we're counted in, remembered so a rack renamed mid-run can't
    // leave the count unbalanced.
    private string _joinedGroup;
    private string _joinedRate;

    // Which of the two counts we are in, remembered with the group and rate:
    // a window that is silenced while flashing has to come off the audible
    // count it joined, not the one it would join now.
    private bool _joinedAudible;
    private bool _showing;
    private bool _applied;

    public string FlashGroup => _rack != null ? _rack.FlashGroup : _flashGroup;

    // Which SART cluster works this window, from the rack it sits in. A loose
    // window in no rack answers only to a master cluster - it has no panel in
    // front of it to be commanded by.
    public string SartGroup => _rack != null ? _rack.SartGroup : "";

    private void Awake()
    {
        _rack = GetComponentInParent<AnnunciatorRack>();
    }

    private void OnEnable()
    {
        _applied = false;   // materials may have been swapped while we were off
        Refresh();
    }

    private void OnDisable()
    {
        LeaveGroup();
    }

    private void Update()
    {
        // A rack drives the phase for all of its windows at once; a loose
        // window has to watch the clock itself.
        if (_rack != null || _joinedGroup == null)
            return;

        ApplyPhase(AnnunciatorFlashGroups.IsLit(FlashGroup, AnnunciatorFlashGroups.AnnounceRate),
                   AnnunciatorFlashGroups.IsLit(FlashGroup, AnnunciatorFlashGroups.ClearRate));
    }

    // ------------------------------------------------------------------ state

    // What IoSync calls with the server's entry for this window.
    public void SetServerState(string state, bool flashing, string flashRate,
                               bool silenced = false)
    {
        string rate = AnnunciatorFlashGroups.NormalizeRate(flashRate);

        if (State == state && Flashing == flashing && FlashRate == rate
                && Silenced == silenced && _applied && !InLampTest)
            return;

        State = state;
        Lit = ParseLit(state);
        Flashing = flashing;
        FlashRate = rate;
        Silenced = silenced;
        Refresh();
    }

    // Light a window without a server, for testing a rack on its own.
    public void SetLocalState(bool lit, bool flashing,
                              string flashRate = AnnunciatorFlashGroups.AnnounceRate)
    {
        State = lit ? "alarm" : "clear";
        Lit = lit;
        Flashing = flashing;
        FlashRate = AnnunciatorFlashGroups.NormalizeRate(flashRate);
        Silenced = false;   // no server, no SART: a local flash sounds
        Refresh();
    }

    // Lamp test: every window lit and steady while it's on, and back to
    // whatever the server last said when it goes off.
    public void SetLampTest(bool on)
    {
        if (InLampTest == on)
            return;

        InLampTest = on;
        Refresh();
    }

    public static bool ParseLit(string state)
    {
        if (string.IsNullOrWhiteSpace(state))
            return false;

        string name = state.Trim().ToLowerInvariant();
        foreach (string dark in DarkStates)
            if (name == dark)
                return false;

        return true;
    }

    // ------------------------------------------------------------- appearance

    // Called by the rack when the group's phase flips.
    public void ApplyPhase(bool announceLit, bool clearLit)
    {
        if (_joinedGroup == null)
            return;   // not flashing, so neither phase is any of our business

        Show(_joinedRate == AnnunciatorFlashGroups.ClearRate ? clearLit : announceLit);
    }

    private void Refresh()
    {
        // Only a lit window flashes, and a lamp test is a steady light.
        bool participates = Lit && Flashing && !InLampTest && isActiveAndEnabled;

        if (participates)
            JoinGroup();
        else
            LeaveGroup();

        bool show = InLampTest
                    || (Lit && (!participates || AnnunciatorFlashGroups.IsLit(FlashGroup, FlashRate)));
        Show(show);
    }

    private void Show(bool lit)
    {
        if (_applied && _showing == lit)
            return;

        _showing = lit;
        _applied = true;

        Material material = lit ? _litMaterial : _unlitMaterial;
        if (_lens == null || material == null || _lens.sharedMaterial == material)
            return;

        // sharedMaterial, not material: these are the assets the builder
        // generated, shared by every window of this colour. Assigning one only
        // points the renderer at it - nothing here edits an asset.
        _lens.sharedMaterial = material;
    }

    private void JoinGroup()
    {
        string group = FlashGroup;
        bool audible = !Silenced;

        // The rate is part of what we joined: a window going from alarm to
        // ringback moves from one clock to the other, and the count on each has
        // to follow it or the resync and the horn both go wrong.
        if (_joinedGroup == group && _joinedRate == FlashRate
                && _joinedAudible == audible)
            return;

        // Silenced, or un-silenced, without otherwise moving: that is a change
        // of count on the SAME clock, so it must not leave and rejoin. Only the
        // audible count moves, and the lamp carries on mid-blink.
        if (_joinedGroup == group && _joinedRate == FlashRate)
        {
            AnnunciatorFlashGroups.SetAudible(group, FlashRate, audible);
            _joinedAudible = audible;
            return;
        }

        LeaveGroup();
        _joinedGroup = group;
        _joinedRate = FlashRate;
        _joinedAudible = audible;
        AnnunciatorFlashGroups.AddFlashing(group, _joinedRate, audible);
    }

    private void LeaveGroup()
    {
        if (_joinedGroup == null)
            return;

        AnnunciatorFlashGroups.RemoveFlashing(_joinedGroup, _joinedRate, _joinedAudible);
        _joinedGroup = null;
        _joinedRate = null;
    }

    // ----------------------------------------------------------------- editor

    // Filled in by the rack builder. Editor-time only - at runtime a window is
    // whatever the rack it was built from made it.
    public void Configure(string uid, string id, string legend,
                          AnnunciatorRackDefinition.TileColor color, string flashGroup,
                          MeshRenderer lens, Material litMaterial, Material unlitMaterial)
    {
        _uid = uid;
        _id = id;
        _legend = legend;
        _color = color;
        _flashGroup = flashGroup;
        _lens = lens;
        _litMaterial = litMaterial;
        _unlitMaterial = unlitMaterial;
    }
}
