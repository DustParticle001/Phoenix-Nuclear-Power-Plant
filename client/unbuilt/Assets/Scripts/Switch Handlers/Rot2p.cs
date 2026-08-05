using UnityEngine;

public class Rot2p : MonoBehaviour, ISwitchControl
{
    public enum SplitAxis { X, Y, Z }

    // Position names the server knows this switch by; order matches IsOn.
    private static readonly string[] _positionNames = { "off", "on" };

    [Header("Identity")]
    [SerializeField] private SwitchDefinition _definition;
    public SwitchDefinition Definition => _definition;
    public string Id => _definition != null ? _definition.Id : "unassigned";

    [Header("Parts")]
    [SerializeField] private Transform _handle;

    [Header("State")]
    [Tooltip("State the switch starts in on scene load.")]
    [SerializeField] private bool _defaultOn = false;

    [Header("Interaction")]
    [SerializeField] private SplitAxis _splitAxis = SplitAxis.X;
    [SerializeField] private bool _invertSides = false;

    [Header("Rotation Config")]
    [SerializeField] private Vector3 _onRotation  = new Vector3(0f, -35f, 0f);
    [SerializeField] private Vector3 _offRotation = new Vector3(0f,  35f, 0f);
    [SerializeField] private float   _speed = 8f;

    private Quaternion _targetRotation;
    public bool IsOn { get; private set; }

    public event System.Action<bool> OnStateChanged;

    // --- ISwitchControl -----------------------------------------------------

    public string[] Positions => _positionNames;
    public string Position => IsOn ? "on" : "off";

    public void SetPosition(string position)
    {
        if (string.Equals(position, "on", System.StringComparison.OrdinalIgnoreCase))
            SetState(true);
        else if (string.Equals(position, "off", System.StringComparison.OrdinalIgnoreCase))
            SetState(false);
        else
            Debug.LogWarning($"[Switch {Id}] ignoring unknown position '{position}'.");
    }

    private void Awake()
    {
        // Set directly (not via SetState) so scene load doesn't fire
        // OnStateChanged before listeners have subscribed.
        IsOn = _defaultOn;
        _targetRotation = Quaternion.Euler(IsOn ? _onRotation : _offRotation);
        _handle.localRotation = _targetRotation;
    }

    private void Update()
    {
        _handle.localRotation = Quaternion.Lerp(
            _handle.localRotation, _targetRotation, Time.deltaTime * _speed);
    }

    public void OnInteract(Vector3 worldHitPoint)
    {
        // Test in the switch body's frame, not the handle's — the handle
        // rotates, which would tilt the left/right split plane with it.
        Vector3 localHit = transform.InverseTransformPoint(worldHitPoint);

        float value = _splitAxis switch
        {
            SplitAxis.X => localHit.x,
            SplitAxis.Y => localHit.y,
            SplitAxis.Z => localHit.z,
            _           => localHit.x
        };

        bool triggered = value >= 0f;
        if (_invertSides) triggered = !triggered;
        SetState(triggered);
    }

    public void SetState(bool on)
    {
        IsOn = on;
        _targetRotation = Quaternion.Euler(IsOn ? _onRotation : _offRotation);
        OnStateChanged?.Invoke(IsOn);
        Debug.Log($"[Switch {Id}] → {(IsOn ? "ON" : "OFF")}");
    }
}