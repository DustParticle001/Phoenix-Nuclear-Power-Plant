using UnityEngine;

// A latching pushbutton: same philosophy as Rot2p, except the moving part
// travels instead of turning. Click it and the cap sinks into the panel and
// stays there; click again and it pops back out. The button that is a state -
// a mode select, a defeat, an isolation.
//
// Two positions only, because a pushbutton has two: there is no such thing as
// a three-position button.
//
// The cap's authored local position is taken as "released", so the modeller
// places the button where it belongs and this only ever pushes it in from
// there. Travel is set as a direction plus a depth rather than a second
// position, so it can be tuned with one number in play mode.
public class Trans2p : MonoBehaviour, ISwitchControl, IInteractable
{
    // Position names the server knows this button by; order matches IsPressed.
    private static readonly string[] _positionNames = { "released", "pressed" };

    [Header("Identity")]
    [SerializeField] private SwitchDefinition _definition;
    public SwitchDefinition Definition => _definition;
    // The definition's UID if one is assigned, otherwise a panel above this
    // control may name it - see IControlIdSource.
    public string Id => ControlId.Resolve(this, _definition);

    [Header("Parts")]
    [Tooltip("The cap - the part that travels. Same field as a switch's handle.")]
    [SerializeField] private Transform _handle;

    [Header("State")]
    [Tooltip("State the button starts in on scene load.")]
    [SerializeField] private bool _defaultPressed = false;

    [Header("Travel Config")]
    [Tooltip("Local direction the cap travels when pressed, in the space it " +
             "sits in. Negate it if the button pops out instead of sinking in.")]
    [SerializeField] private Vector3 _pressAxis = Vector3.back;

    [Tooltip("How far the cap travels, in metres.")]
    [SerializeField] private float _pressDepth = 0.004f;

    [SerializeField] private float _speed = 25f;

    private Vector3 _releasedPosition;
    private Vector3 _targetPosition;

    public bool IsPressed { get; private set; }

    public event System.Action<bool> OnStateChanged;

    // --- ISwitchControl -----------------------------------------------------

    public string[] Positions => _positionNames;
    public string Position => IsPressed ? "pressed" : "released";

    public void SetPosition(string position)
    {
        if (string.Equals(position, "pressed", System.StringComparison.OrdinalIgnoreCase))
            SetState(true);
        else if (string.Equals(position, "released", System.StringComparison.OrdinalIgnoreCase))
            SetState(false);
        else
            Debug.LogWarning($"[Button {Id}] ignoring unknown position '{position}'.");
    }

    private void Awake()
    {
        // Read the released pose before anything moves the cap: it is the
        // authored position, and pressing is measured from it.
        _releasedPosition = _handle.localPosition;

        // Set directly (not via SetState) so scene load doesn't fire
        // OnStateChanged before listeners have subscribed.
        IsPressed = _defaultPressed;
        _targetPosition = PositionFor(IsPressed);
        _handle.localPosition = _targetPosition;
    }

    private void Update()
    {
        _handle.localPosition = Vector3.Lerp(
            _handle.localPosition, _targetPosition, Time.deltaTime * _speed);
    }

    // --- IInteractable ------------------------------------------------------

    // A button has no sides: the whole cap does the one thing it does, so the
    // hit point is nothing to it.
    public void OnInteract(Vector3 worldHitPoint) => SetState(!IsPressed);

    public void SetState(bool pressed)
    {
        if (IsPressed == pressed)
            return;

        IsPressed = pressed;
        _targetPosition = PositionFor(IsPressed);
        OnStateChanged?.Invoke(IsPressed);
        Debug.Log($"[Button {Id}] → {(IsPressed ? "PRESSED" : "RELEASED")}");
    }

    // Normalized, so a hand-typed axis that isn't unit length doesn't quietly
    // scale the depth along with it.
    private Vector3 PositionFor(bool pressed) =>
        pressed ? _releasedPosition + _pressAxis.normalized * _pressDepth
                : _releasedPosition;
}
