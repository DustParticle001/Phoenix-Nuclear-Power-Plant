using UnityEngine;

// Drives the Red/Green lamp pair on a switch. Mirrors the state of a Rot2p
// switch: ON → Red lit / Green dark, OFF → Red dark / Green lit.
// Add this to the "switch lamps" object.
public class SwitchLampIndicator : MonoBehaviour
{
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
            _redUnlit = _redMesh.sharedMaterial;
        if (_greenUnlit == null && _greenMesh != null)
            _greenUnlit = _greenMesh.sharedMaterial;
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

    private void Apply(bool isOn)
    {
        bool redLit = _invertColors ? !isOn : isOn;

        if (_redMesh != null)
            _redMesh.sharedMaterial = redLit ? _redLit : _redUnlit;
        if (_greenMesh != null)
            _greenMesh.sharedMaterial = redLit ? _greenUnlit : _greenLit;
    }
}
