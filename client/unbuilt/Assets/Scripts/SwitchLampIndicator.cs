using UnityEngine;

// Drives the Red/Green lamp pair on a switch. Mirrors the state of a Rot2p
// switch: ON → Red lit / Green dark, OFF → Red dark / Green lit.
// Add this to the "switch lamps" object.
//
// Nothing below has to be wired up. Assign what the lamp actually has - one
// mesh or two, and whichever of the four materials exist. A half with no mesh
// is skipped, a material left empty leaves that mesh wearing what it already
// has, meshes are auto-found by child name ("Red"/"Green") or failing that
// taken as the only mesh under this object, and the lens slot falls back to
// the mesh's last material slot. A partly-filled lamp works; it shows less.
//
// It also does a SINGLE lamp standing on its own - a pump run light on the
// panel rather than a pair on a switch. Leave the green mesh empty, give it no
// definition and hang it under no switch, and it answers to its own object's
// name with nothing but the server driving it. See Id.
//
// Once the server sends a state for this indicator (SetServerState, driven by
// IoSync), the server owns the lamps and the local switch stops driving them —
// a lamp can be lit for reasons the switch position doesn't show.
public class SwitchLampIndicator : MonoBehaviour
{
    public enum LampState { Off, Red, Green }

    // Flash half-period. A lit lamp alternates lit/dark while flashing.
    private const float FlashSeconds = 0.35f;

    [Header("Binding")]
    [Tooltip("Definition (UID) of the switch to mirror. Leave empty to bind to the switch this lamp is a child of.")]
    [SerializeField] private SwitchDefinition _definition;

    [Tooltip("Swap the mapping: ON → Green lit, OFF → Red lit.")]
    [SerializeField] private bool _invertColors = false;

    [Header("Lamp Meshes")]
    [Tooltip("Both optional. Auto-found by child name (\"Red\"/\"Green\") if left empty, "
        + "or the only mesh under this object if neither name matches.")]
    [SerializeField] private MeshRenderer _redMesh;
    [SerializeField] private MeshRenderer _greenMesh;

    [Header("Materials")]
    [Tooltip("All optional. Unlit falls back to whatever the mesh currently wears; "
        + "a missing Lit material just leaves that lamp dark.")]
    [SerializeField] private Material _redUnlit;   // Lamp Red
    [SerializeField] private Material _redLit;     // Lamp Red Lit
    [SerializeField] private Material _greenUnlit; // Lamp Green
    [SerializeField] private Material _greenLit;   // Lamp Green Lit

    private Rot2p _switch;

    private bool _serverDriven;
    private LampState _serverState = LampState.Off;
    private bool _flashing;
    private float _flashTimer;
    private bool _flashLit = true;

    // The lamp meshes use two material slots; the lens colour is slot 1.
    private const int LampMaterialIndex = 1;

    // UID this indicator answers to, in order: its own definition, the switch
    // it hangs under, and failing both its own object's name. IoSync looks it
    // up by this.
    //
    // A definition asset whose id was never generated counts as no definition
    // at all - "Generate New ID" is a manual step and it is easy to add the
    // asset and forget it. Reading its empty id would register the lamp under
    // "", which matches nothing the server sends and fails silently.
    //
    // The last one is for a lamp that is nobody's pair - a run light sitting on
    // the panel, which has no switch above it and would otherwise be skipped
    // silently. The object name is a real uid on the server, so renaming the
    // object renames it there too; give it a definition if you want a name that
    // survives being renamed.
    public string Id
    {
        get
        {
            if (_definition != null && !string.IsNullOrWhiteSpace(_definition.Id))
                return _definition.Id;

            // Inactive included: IoSync's scan finds controls on inactive
            // objects, and a lamp it can see has to resolve the same way.
            var owner = GetComponentInParent<ISwitchControl>(true);
            if (owner != null)
                return owner.Id;

            return !string.IsNullOrWhiteSpace(name) ? name.Trim() : "unassigned";
        }
    }

    // Editor-only: runs when the component is first added (or Reset is clicked).
    private void Reset()
    {
        var sw = GetComponentInParent<Rot2p>();
        if (sw != null && sw.Definition != null)
            _definition = sw.Definition;
    }

    private void Start()
    {
        ResolveMeshes();

        _switch = FindSwitch();
        if (_switch == null)
        {
            // Three ways to have no local switch to mirror, and only one is a
            // mistake. A lamp with no definition and nothing above it is a
            // panel light the server drives alone - a pump run light. A lamp on
            // a switch that isn't a Rot2p has nothing local to follow either: a
            // spring-return controller has no on/off, it has two momentary
            // ends, and the server names the lamp outright. Both are ways of
            // using this. Naming a switch that nothing answers to is not.
            if (_definition != null && !AnySwitchAnswersTo(_definition.Id))
                Debug.LogWarning(
                    $"[SwitchLampIndicator] '{name}' found no switch with ID {_definition.Id}.");

            return;
        }

        _switch.OnStateChanged += Apply;
        Apply(_switch.IsOn);
    }

    private void OnDestroy()
    {
        if (_switch != null)
            _switch.OnStateChanged -= Apply;
    }

    private void ResolveMeshes()
    {
        var meshes = GetComponentsInChildren<MeshRenderer>(true);

        foreach (var renderer in meshes)
        {
            if (_redMesh == null && renderer.name.Equals("Red", System.StringComparison.OrdinalIgnoreCase))
                _redMesh = renderer;
            else if (_greenMesh == null && renderer.name.Equals("Green", System.StringComparison.OrdinalIgnoreCase))
                _greenMesh = renderer;
        }

        // Nothing assigned and nothing named Red or Green: a lamp that is just
        // a lamp. If there is exactly one mesh to be had, that is it, and it
        // takes the red role - a single lamp is lit/dark, and Apply drives red
        // for "on". Two or more and we would be guessing which is which, so
        // leave them alone rather than pick wrong.
        if (_redMesh == null && _greenMesh == null && meshes.Length == 1)
            _redMesh = meshes[0];

        if (_redUnlit == null && _redMesh != null)
            _redUnlit = GetLampMaterial(_redMesh);
        if (_greenUnlit == null && _greenMesh != null)
            _greenUnlit = GetLampMaterial(_greenMesh);
    }

    // The lens slot on a lamp mesh: slot 1 on the two-slot lamps in the scene,
    // but a mesh carrying fewer takes its last slot rather than being skipped.
    private static int LampSlot(Material[] materials)
    {
        return materials.Length > LampMaterialIndex
            ? LampMaterialIndex
            : materials.Length - 1;
    }

    private Material GetLampMaterial(MeshRenderer renderer)
    {
        var materials = renderer.sharedMaterials;
        return materials.Length > 0 ? materials[LampSlot(materials)] : null;
    }

    private void SetLampMaterial(MeshRenderer renderer, Material material)
    {
        // No material for this state - leave the mesh wearing what it has. A
        // lamp with no Lit material assigned simply never lights.
        if (material == null)
            return;

        var materials = renderer.sharedMaterials;
        if (materials.Length == 0)
            return;

        int slot = LampSlot(materials);
        if (materials[slot] == material)
            return;

        materials[slot] = material;
        renderer.sharedMaterials = materials;
    }

    // Any control answering to this id, Rot2p or not. Only asked on the path
    // where no Rot2p matched, so the cost lands once and only on a lamp that
    // would otherwise be warned about.
    private static bool AnySwitchAnswersTo(string id)
    {
        foreach (var behaviour in FindObjectsByType<MonoBehaviour>(
                     FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (behaviour is ISwitchControl control && control.Id == id)
                return true;

        return false;
    }

    private Rot2p FindSwitch()
    {
        if (_definition == null)
            return GetComponentInParent<Rot2p>();

        foreach (var sw in FindObjectsByType<Rot2p>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (sw.Id == _definition.Id)
                return sw;

        return null;
    }

    private void Update()
    {
        if (!_serverDriven || !_flashing)
            return;

        _flashTimer += Time.deltaTime;
        if (_flashTimer < FlashSeconds)
            return;

        _flashTimer = 0f;
        _flashLit = !_flashLit;
        ApplyServerState();
    }

    // Called by IoSync with what the server holds for this indicator. State
    // names are the server's: "red", "green", anything else reads as dark.
    // _invertColors is not applied here - the server names the lamp outright.
    public void SetServerState(string state, bool flashing)
    {
        LampState lamp = ParseState(state);

        if (_serverDriven && lamp == _serverState && flashing == _flashing)
            return;

        _serverDriven = true;
        _serverState = lamp;
        _flashing = flashing;
        _flashTimer = 0f;
        _flashLit = true;
        ApplyServerState();
    }

    // Hand the lamps back to the local switch (used when a session ends).
    public void ClearServerState()
    {
        if (!_serverDriven)
            return;

        _serverDriven = false;
        _flashing = false;
        if (_switch != null)
            Apply(_switch.IsOn);
    }

    private static LampState ParseState(string state)
    {
        if (string.Equals(state, "red", System.StringComparison.OrdinalIgnoreCase))
            return LampState.Red;
        if (string.Equals(state, "green", System.StringComparison.OrdinalIgnoreCase))
            return LampState.Green;

        return LampState.Off;
    }

    private void ApplyServerState()
    {
        bool lit = !_flashing || _flashLit;
        ApplyLamps(lit && _serverState == LampState.Red,
                   lit && _serverState == LampState.Green);
    }

    private void Apply(bool isOn)
    {
        // The server has the last word once it has spoken.
        if (_serverDriven)
            return;

        bool redLit = _invertColors ? !isOn : isOn;
        ApplyLamps(redLit, !redLit);
    }

    private void ApplyLamps(bool redLit, bool greenLit)
    {
        if (_redMesh != null)
            SetLampMaterial(_redMesh, redLit ? _redLit : _redUnlit);
        if (_greenMesh != null)
            SetLampMaterial(_greenMesh, greenLit ? _greenLit : _greenUnlit);
    }
}
