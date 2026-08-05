using UnityEngine;

// Drives the Red/Green lamp pair on a switch. Mirrors the state of a Rot2p
// switch: ON → Red lit / Green dark, OFF → Red dark / Green lit.
// Add this to the "switch lamps" object.
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
    [Tooltip("Auto-found by child name (\"Red\"/\"Green\") if left empty.")]
    [SerializeField] private MeshRenderer _redMesh;
    [SerializeField] private MeshRenderer _greenMesh;

    [Header("Materials")]
    [Tooltip("Unlit materials fall back to whatever the mesh currently uses if left empty.")]
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

    // UID this indicator answers to: its own definition if set, otherwise the
    // switch it hangs under. IoSync looks it up by this.
    public string Id
    {
        get
        {
            if (_definition != null)
                return _definition.Id;

            var owner = GetComponentInParent<ISwitchControl>();
            return owner != null ? owner.Id : "unassigned";
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
            Debug.LogWarning(
                $"[SwitchLampIndicator] '{name}' could not find a Rot2p switch " +
                (_definition != null ? $"with ID {_definition.Id}" : "in its parents") + ".");
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
        foreach (var renderer in GetComponentsInChildren<MeshRenderer>(true))
        {
            if (_redMesh == null && renderer.name.Equals("Red", System.StringComparison.OrdinalIgnoreCase))
                _redMesh = renderer;
            else if (_greenMesh == null && renderer.name.Equals("Green", System.StringComparison.OrdinalIgnoreCase))
                _greenMesh = renderer;
        }

        if (_redUnlit == null && _redMesh != null)
            _redUnlit = GetLampMaterial(_redMesh);
        if (_greenUnlit == null && _greenMesh != null)
            _greenUnlit = GetLampMaterial(_greenMesh);
    }

    private Material GetLampMaterial(MeshRenderer renderer)
    {
        var materials = renderer.sharedMaterials;
        return materials.Length > LampMaterialIndex ? materials[LampMaterialIndex] : null;
    }

    private void SetLampMaterial(MeshRenderer renderer, Material material)
    {
        if (material == null)
            return;

        var materials = renderer.sharedMaterials;
        if (materials.Length <= LampMaterialIndex)
        {
            Debug.LogWarning(
                $"[SwitchLampIndicator] '{renderer.name}' has {materials.Length} material slot(s); " +
                $"expected at least {LampMaterialIndex + 1}.");
            return;
        }

        materials[LampMaterialIndex] = material;
        renderer.sharedMaterials = materials;
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
