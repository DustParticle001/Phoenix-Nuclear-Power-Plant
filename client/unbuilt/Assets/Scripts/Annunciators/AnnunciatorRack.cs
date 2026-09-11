// AnnunciatorRack.cs
using System.Collections.Generic;
using UnityEngine;

// The rack a set of annunciator windows sits in: the model the builder
// generated, the windows on it, and the flash group they belong to.
//
// Two racks with the same group name flash as one panel - that's the whole
// point of the group, and why the phase lives in AnnunciatorFlashGroups rather
// than here. This component reads the group's phase once a frame and pushes it
// to its own windows, so a rack with sixty windows costs one clock read.
//
// Built by Editor/AnnunciatorRackBuilder.cs from an AnnunciatorRackDefinition.
// Rebuild the definition and every instance of its prefab follows.
[DisallowMultipleComponent]
public class AnnunciatorRack : MonoBehaviour
{
    [Header("Identity")]
    [SerializeField] private AnnunciatorRackDefinition _definition;

    [Tooltip("Flash with a different group than the definition says. Empty = the definition's group.")]
    [SerializeField] private string _flashGroupOverride = "";

    [Tooltip("Answer to a different SART cluster than the definition says. Empty = the definition's.")]
    [SerializeField] private string _sartGroupOverride = "";

    [Header("Windows")]
    [Tooltip("Filled in by the builder, in the definition's order (row-major from the top-left).")]
    [SerializeField] private AnnunciatorTile[] _tiles = new AnnunciatorTile[0];

    [Header("Testing")]
    [Tooltip("Lights every window, steady, without a server. Turn it off to hand them back to the server.")]
    [SerializeField] private bool _lampTest = false;

    public AnnunciatorRackDefinition Definition => _definition;
    public IReadOnlyList<AnnunciatorTile> Tiles => _tiles;
    public int TileCount => _tiles != null ? _tiles.Length : 0;

    // The group this rack flashes with. Override first, then the definition,
    // then the default group - so racks that were never given a group still
    // flash together rather than each on their own clock.
    public string FlashGroup
    {
        get
        {
            if (!string.IsNullOrWhiteSpace(_flashGroupOverride))
                return _flashGroupOverride.Trim();

            if (_definition != null && !string.IsNullOrWhiteSpace(_definition.flashGroup))
                return _definition.flashGroup.Trim();

            return AnnunciatorFlashGroups.DefaultGroup;
        }
    }

    // Which SART cluster works this rack. Nothing like FlashGroup's default:
    // a rack nobody has assigned to a panel is reached only by a master
    // cluster, because guessing which of several panels commands it would be
    // worse than saying nothing. Override first, then the definition.
    //
    // This is a SEPARATE grouping from the flash group, and coarser the other
    // way round: every rack in a control room flashes in step, while a SART
    // panel commands the one to three racks in front of it. Sharing one name
    // for both would tie the panel you can reach to the panel you can see.
    public string SartGroup
    {
        get
        {
            if (!string.IsNullOrWhiteSpace(_sartGroupOverride))
                return _sartGroupOverride.Trim();

            if (_definition != null && !string.IsNullOrWhiteSpace(_definition.sartGroup))
                return _definition.sartGroup.Trim();

            return "";
        }
    }

    public float AnnounceFlashSeconds => _definition != null
        ? _definition.announceFlashSeconds
        : AnnunciatorFlashGroups.DefaultAnnounceHalfPeriod;

    public float ClearFlashSeconds => _definition != null
        ? _definition.clearFlashSeconds
        : AnnunciatorFlashGroups.DefaultClearHalfPeriod;

    private string _declaredGroup;
    private bool _announceLit = true;
    private bool _clearLit = true;
    private bool _lampTestApplied;

    private void OnEnable()
    {
        DeclareGroup();
        _lampTestApplied = !_lampTest;   // force the first Update to apply it
    }

    private void Update()
    {
        // The group can be re-pointed from the Inspector while the game runs.
        if (_declaredGroup != FlashGroup)
            DeclareGroup();

        if (_lampTestApplied != _lampTest)
        {
            _lampTestApplied = _lampTest;
            SetLampTest(_lampTest);
        }

        // Two clocks now - a window follows whichever one its rate names.
        // Both are read once here, so a rack with sixty windows still costs
        // two clock reads a frame rather than sixty.
        bool announceLit = AnnunciatorFlashGroups.IsLit(FlashGroup, AnnunciatorFlashGroups.AnnounceRate);
        bool clearLit = AnnunciatorFlashGroups.IsLit(FlashGroup, AnnunciatorFlashGroups.ClearRate);

        if (announceLit == _announceLit && clearLit == _clearLit)
            return;

        _announceLit = announceLit;
        _clearLit = clearLit;

        foreach (AnnunciatorTile tile in _tiles)
        {
            if (tile != null)
                tile.ApplyPhase(announceLit, clearLit);
        }
    }

    // --------------------------------------------------------------- windows

    // By uid, or by the readable id the legend was slugged into.
    public AnnunciatorTile Find(string uidOrId)
    {
        if (string.IsNullOrEmpty(uidOrId) || _tiles == null)
            return null;

        foreach (AnnunciatorTile tile in _tiles)
        {
            if (tile == null)
                continue;

            if (tile.Id == uidOrId ||
                string.Equals(tile.ReadableId, uidOrId, System.StringComparison.OrdinalIgnoreCase))
                return tile;
        }

        return null;
    }

    [ContextMenu("Lamp Test")]
    private void LampTestOn() => SetLampTest(true);

    // The panel's off switch: every window dark AND the lamp test dropped.
    // Turning the windows out while a lamp test was still on would leave the
    // whole rack lit and look like the off switch had done nothing.
    [ContextMenu("Lamps Off")]
    public void LampsOff()
    {
        SetLampTest(false);
        SetAllLocal(false, false);
    }

    // Every window in, unacknowledged: the fast flash, and the horn with it.
    [ContextMenu("Flash All (announce)")]
    public void FlashAll() => SetAllLocal(true, true, AnnunciatorFlashGroups.AnnounceRate);

    // Every window ringing back: cleared but unacknowledged, on the slow
    // flash. What the panel looks like after a transient nobody caught.
    [ContextMenu("Flash All (ringback)")]
    public void RingbackAll() => SetAllLocal(true, true, AnnunciatorFlashGroups.ClearRate);

    // Every window lit and steady - the check an operator does before a shift.
    // Turning it off hands the windows back to whatever the server last said.
    public void SetLampTest(bool on)
    {
        _lampTest = on;
        _lampTestApplied = on;

        foreach (AnnunciatorTile tile in _tiles)
        {
            if (tile != null)
                tile.SetLampTest(on);
        }
    }

    // Drive every window locally, for looking at a rack with no server behind it.
    public void SetAllLocal(bool lit, bool flashing,
                            string flashRate = AnnunciatorFlashGroups.AnnounceRate)
    {
        foreach (AnnunciatorTile tile in _tiles)
        {
            if (tile != null)
                tile.SetLocalState(lit, flashing, flashRate);
        }
    }

    private void DeclareGroup()
    {
        _declaredGroup = FlashGroup;
        AnnunciatorFlashGroups.Declare(_declaredGroup, AnnunciatorFlashGroups.AnnounceRate, AnnounceFlashSeconds);
        AnnunciatorFlashGroups.Declare(_declaredGroup, AnnunciatorFlashGroups.ClearRate, ClearFlashSeconds);
        _announceLit = AnnunciatorFlashGroups.IsLit(_declaredGroup, AnnunciatorFlashGroups.AnnounceRate);
        _clearLit = AnnunciatorFlashGroups.IsLit(_declaredGroup, AnnunciatorFlashGroups.ClearRate);
    }

    // ----------------------------------------------------------------- editor

    // Filled in by the rack builder.
    public void Configure(AnnunciatorRackDefinition definition, AnnunciatorTile[] tiles)
    {
        _definition = definition;
        _tiles = tiles ?? new AnnunciatorTile[0];
    }
}
